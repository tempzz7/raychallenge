import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
from googleapiclient.discovery import build
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from googleapiclient.errors import HttpError
from ratelimit import limits, sleep_and_retry


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('f1_analytics.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.getenv('YOUTUBE_API_KEY')
PLAYLIST_ID = os.getenv('PLAYLIST_ID')

logger.info(f"API_KEY carregada: {'Sim' if API_KEY else 'Não'}")
logger.info(f"PLAYLIST_ID carregada: {'Sim' if PLAYLIST_ID else 'Não'}")

if not API_KEY or not PLAYLIST_ID:
    logger.error("Variáveis de ambiente não configuradas corretamente")
    raise ValueError("YOUTUBE_API_KEY e PLAYLIST_ID devem ser configuradas no arquivo .env")

class YouTubeAnalytics:
    # Define rate limits: 10000 calls per day = ~7 calls per minute
    CALLS = 7
    RATE_PERIOD = 60  # 1 minute in seconds

    @sleep_and_retry
    @limits(calls=CALLS, period=RATE_PERIOD)
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _inicializar_servico(self) -> Any:
        try:
            service = build('youtube', 'v3', developerKey=API_KEY)
            logger.info("Serviço do YouTube iniciado com sucesso.")
            return service
        except HttpError as e:
            if e.resp.status == 403:
                logger.error("Erro de autorização com a API do YouTube. Verifique sua chave API.")
                raise
            elif e.resp.status == 429:
                logger.error("Limite de cota da API do YouTube atingido.")
                raise
            else:
                logger.error(f"Erro HTTP ao iniciar serviço do YouTube: {e}")
                raise
        except Exception as e:
            logger.error(f"Erro inesperado ao iniciar o serviço do YouTube: {e}")
            raise
    
    def __init__(self):
        self.service = self._inicializar_servico()
        self.videos = []
        self.df = None
    
    @sleep_and_retry
    @limits(calls=CALLS, period=RATE_PERIOD)
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def coletar_videos_playlist(self, playlist_id: str) -> List[Dict]:
        videos = []
        next_page_token = None
        page_count = 0
        
        logger.info(f"Iniciando coleta de vídeos da playlist: {playlist_id}")
        
        while True:
            try:
                page_count += 1
                logger.info(f"Coletando página {page_count}")
                
                request = self.service.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
                
                if not response.get('items'):
                    logger.warning("Nenhum item encontrado na resposta da API")
                    break
                    
                current_page_videos = response.get('items', [])
                videos.extend(current_page_videos)
                logger.info(f"Vídeos coletados na página {page_count}: {len(current_page_videos)}")
                
                for video in current_page_videos:
                    title = video.get('snippet', {}).get('title', 'Sem título')
                    logger.info(f"Vídeo encontrado: {title}")
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    logger.info("Não há mais páginas para coletar")
                    break
                    
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    logger.error(f"Erro de API ao coletar vídeos (status {e.resp.status})")
                    raise
                else:
                    logger.error(f"Erro HTTP ao coletar vídeos: {e}")
                    break
            except Exception as e:
                logger.error(f"Erro ao obter vídeos da playlist: {str(e)}")
                break
        
        logger.info(f"Total de vídeos obtidos: {len(videos)}")
        return videos
    
    @sleep_and_retry
    @limits(calls=CALLS, period=RATE_PERIOD)
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def obter_detalhes_videos(self, video_ids: List[str]) -> List[Dict]:
        details = []
        logger.info(f"Iniciando coleta de detalhes para {len(video_ids)} vídeos")
        
        for i in range(0, len(video_ids), 50):
            try:
                batch = video_ids[i:i+50]
                logger.info(f"Processando batch de {len(batch)} vídeos")
                
                request = self.service.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=','.join(batch)
                )
                response = request.execute()
                
                if not response.get('items'):
                    logger.warning(f"Nenhum item encontrado para o batch {i//50 + 1}")
                    continue
                    
                details.extend(response.get('items', []))
                logger.info(f"Detalhes obtidos para {len(response.get('items', []))} vídeos do batch {i//50 + 1}")
                
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    logger.error(f"Erro de API ao obter detalhes dos vídeos (status {e.resp.status})")
                    raise
                else:
                    logger.error(f"Erro HTTP ao obter detalhes dos vídeos: {e}")
                    continue
            except Exception as e:
                logger.error(f"Erro ao obter detalhes dos vídeos do batch {i//50 + 1}: {str(e)}")
                continue
        
        logger.info(f"Total de detalhes obtidos: {len(details)}")
        return details
    
    def processar_dados(self, video_details: List[Dict]) -> pd.DataFrame:
        dados_processados = []
        
        logger.info(f"Iniciando processamento de {len(video_details)} vídeos")
        
        for item in video_details:
            snippet = item.get('snippet', {})
            stats = item.get('statistics', {})
            content_details = item.get('contentDetails', {})
            
            if not all([snippet, stats, content_details]):
                logger.warning(f"Vídeo {item.get('id', 'N/A')} está faltando dados")
                continue
            
            try:
                data_publicacao = datetime.strptime(
                    snippet.get('publishedAt', '1970-01-01T00:00:00Z'),
                    '%Y-%m-%dT%H:%M:%SZ'
                )
                
                logger.info(f"Processando vídeo de {data_publicacao.strftime('%Y-%m-%d')}")
                
                duration = content_details.get('duration', 'N/A')
                try:
                    duration_timedelta = pd.to_timedelta(duration).total_seconds()
                    duration_readable = str(timedelta(seconds=duration_timedelta))
                except Exception:
                    duration_readable = 'N/A'
                
                descricao = snippet.get('description', '')
                tags = snippet.get('tags', [])
                
                dados_processados.append({
                    'video_id': item.get('id'),
                    'titulo': snippet.get('title', 'N/A'),
                    'data_publicacao': data_publicacao,
                    'visualizacoes': int(stats.get('viewCount', 0)),
                    'curtidas': int(stats.get('likeCount', 0)),
                    'comentarios': int(stats.get('commentCount', 0)),
                    'duracao': duration_readable,
                    'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                    'descricao': descricao,
                    'tags': ','.join(tags) if tags else 'N/A',
                    'canal': snippet.get('channelTitle', 'N/A')
                })
                
                logger.info(f"Vídeo processado com sucesso: {snippet.get('title', 'N/A')}")
                
            except Exception as e:
                logger.warning(f"Erro ao processar vídeo {item.get('id', 'N/A')}: {str(e)}")
                continue
        
        self.df = pd.DataFrame(dados_processados)
        logger.info(f"Dados processados: {len(self.df)} registros")
        
        if not self.df.empty:
            logger.info("Datas dos vídeos processados:")
            for data in self.df['data_publicacao'].unique():
                count = len(self.df[self.df['data_publicacao'] == data])
                logger.info(f"{data.strftime('%Y-%m-%d')}: {count} vídeos")
        
        return self.df
    
    def salvar_dados(self, nome_arquivo: str = 'f1_2024_highlights.csv') -> None:
        if self.df is not None:
            self.df.to_csv(nome_arquivo, index=False, encoding='utf-8-sig')
            logger.info("Dados salvos com sucesso em '%s'!", nome_arquivo)
        else:
            logger.warning("Nenhum dado disponível para salvar.")

def main():
    try:
        logger.info("Iniciando coleta de dados...")
        analisador = YouTubeAnalytics()
        
        playlist_items = analisador.coletar_videos_playlist(PLAYLIST_ID)
        
        if not playlist_items:
            logger.error("Nenhum item encontrado na playlist")
            return
            
        video_ids = []
        for item in playlist_items:
            try:
                video_id = item['snippet']['resourceId']['videoId']
                video_ids.append(video_id)
                logger.info(f"ID de vídeo extraído: {video_id}")
            except KeyError as e:
                logger.warning(f"Erro ao extrair ID do vídeo: {e}")
                continue
                
        logger.info(f"IDs de vídeos extraídos: {len(video_ids)}")
        
        if not video_ids:
            logger.error("Nenhum ID de vídeo válido encontrado")
            return
        
        video_details = analisador.obter_detalhes_videos(video_ids)
        
        if not video_details:
            logger.error("Nenhum detalhe de vídeo obtido")
            return
            
        df = analisador.processar_dados(video_details)
        
        if df.empty:
            logger.error("Nenhum dado processado")
            return
            
        logger.info(f"Total de vídeos antes do filtro de 2024: {len(df)}")
        
        df_2024 = df[
            (df['data_publicacao'].dt.year == 2024) |
            (df['data_publicacao'].dt.year == 2023)  # Incluindo vídeos de 2023 também
        ]
        logger.info(f"Vídeos encontrados (2023-2024): {len(df_2024)}")
        
        if not df_2024.empty:
            logger.info("Datas dos vídeos encontrados:")
            for data in df_2024['data_publicacao'].unique():
                count = len(df_2024[df_2024['data_publicacao'] == data])
                logger.info(f"{data.strftime('%Y-%m-%d')}: {count} vídeos")
        
        analisador.salvar_dados()
        
        logger.info("Coleta de dados concluída com sucesso!")
    except Exception as e:
        logger.error(f"Erro durante a execução do script: {str(e)}")
        raise

if __name__ == "__main__":
    main()
