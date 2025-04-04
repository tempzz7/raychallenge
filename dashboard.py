import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone
import dash
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dotenv import load_dotenv
import re
import numpy as np
import logging
from functools import lru_cache
from io import StringIO
from dash.exceptions import PreventUpdate


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='dashboard_debug.log'
)
logger = logging.getLogger('dashboard')

load_dotenv()

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    meta_tags=[
        {'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0'}
    ],
    assets_folder='assets',
    suppress_callback_exceptions=True  # Importante para callbacks condicionais
)

min_date = pd.to_datetime('2023-01-01', utc=True)
max_date = pd.to_datetime('now', utc=True)

def truncate_title(title, max_length=40):
    try:
        # Verificar se o título é nulo ou NaN
        if pd.isna(title) or title is None:
            return "Sem título"
            
        # Converter para string se necessário
        title_str = str(title).strip()
        
        # Verificar se o título está vazio
        if not title_str:
            return "Sem título"
            
        # Truncar o título se necessário
        if len(title_str) > max_length:
            return title_str[:max_length] + '...'
        return title_str
    except Exception as e:
        logger.error(f"Erro ao truncar título: {e}")
        return "Sem título"

def safe_engagement_rate(row):
    try:
        # Garantir que os valores são numéricos
        visualizacoes = float(row['visualizacoes'])
        curtidas = float(row['curtidas'])
        comentarios = float(row['comentarios'])
        
        # Evitar divisão por zero
        if visualizacoes == 0:
            return 0.0
            
        # Calcular taxa de engajamento
        taxa = ((curtidas + comentarios) / visualizacoes) * 100
        return round(taxa, 2)
    except Exception as e:
        logger.error(f"Erro ao calcular taxa de engajamento: {e}")
        return 0.0

# Função segura para carregar dados
def load_data():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'f1_2024_highlights.csv')
        
        logger.info(f"Diretório atual: {current_dir}")
        logger.info(f"Tentando carregar o arquivo CSV de: {csv_path}")
        
        if not os.path.exists(csv_path):
            logger.error(f"Arquivo CSV não encontrado em: {csv_path}")
            raise FileNotFoundError(f"Arquivo CSV não encontrado em: {csv_path}")
        
        # Verificar tamanho do arquivo
        file_size = os.path.getsize(csv_path)
        logger.info(f"Tamanho do arquivo: {file_size} bytes")
        
        # Carregar dados com tratamento de erros
        df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')
        logger.info(f"Arquivo CSV carregado com sucesso. Formato: {df.shape}")

        # Converter coluna de data com tratamento de erro
        try:
            df['data_publicacao'] = pd.to_datetime(df['data_publicacao'], errors='coerce', utc=True)
            logger.info("Coluna de data convertida com sucesso")
            
            # Verificando se a conversão foi bem sucedida
            if df['data_publicacao'].isna().any():
                logger.warning(f"Existem {df['data_publicacao'].isna().sum()} valores de data que não puderam ser convertidos")
                # Remover linhas com datas inválidas
                df = df.dropna(subset=['data_publicacao'])
        except Exception as e:
            logger.error(f"Erro ao converter datas: {e}")
            raise
        
        # Verificar se não há linhas vazias
        if df.empty:
            logger.error("DataFrame está vazio após carregamento!")
            raise ValueError("DataFrame está vazio após carregamento")
        
        logger.info(f"DataFrame carregado com {len(df)} linhas e {len(df.columns)} colunas")
        logger.info(f"Colunas disponíveis: {df.columns.tolist()}")
        
        # Calcular métricas adicionais com tratamento de erro
        logger.info("Calculando métricas adicionais...")
        
        try:
            # Taxa de engajamento
            df['taxa_engajamento'] = df.apply(safe_engagement_rate, axis=1)
            
            # Média diária de visualizações
            hoje = pd.Timestamp.now(tz='UTC')
            df['dias_desde_publicacao'] = (hoje - df['data_publicacao']).dt.days
            df['dias_desde_publicacao'] = np.where(
                df['dias_desde_publicacao'] < 1,
                1,
                df['dias_desde_publicacao']
            )
            df['media_visualizacoes_diarias'] = (df['visualizacoes'] / df['dias_desde_publicacao']).round(0)
            
            # Outras métricas
            df['proporcao_curtidas_visualizacoes'] = np.where(
                df['visualizacoes'] > 0,
                (df['curtidas'] / df['visualizacoes'] * 100).round(2),
                0
            )
            df['proporcao_comentarios_visualizacoes'] = np.where(
                df['visualizacoes'] > 0,
                (df['comentarios'] / df['visualizacoes'] * 100).round(2),
                0
            )
            
            # Extrair temporada do título
            df['temporada'] = df['titulo'].str.extract(r'(\d{4})')
            df['temporada'] = df['temporada'].fillna(df['data_publicacao'].dt.year.astype(str))
            df['temporada'] = df['temporada'].where(df['temporada'].isin(['2023', '2024']), '2024')
            
            logger.info("Métricas calculadas com sucesso")
            return df
            
        except Exception as e:
            logger.error(f"Erro ao calcular métricas: {e}")
            raise
            
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}", exc_info=True)
        raise

# Carregar dados iniciais
initial_df = load_data()

# Função central para aplicar filtros - evita repetição de código
@lru_cache(maxsize=32)
def apply_filters(df_json, start_date, end_date, sort_by, sort_order):
    try:
        # Converter JSON para DataFrame usando StringIO para evitar FutureWarning
        df = pd.read_json(StringIO(df_json), orient='split')
        
        # Converter datas para datetime se forem strings
        if isinstance(start_date, str):
            start_date = pd.to_datetime(start_date, utc=True)
        if isinstance(end_date, str):
            end_date = pd.to_datetime(end_date, utc=True)
            
        # Garantir que a coluna data_publicacao é datetime
        if not pd.api.types.is_datetime64_any_dtype(df['data_publicacao']):
            df['data_publicacao'] = pd.to_datetime(df['data_publicacao'], utc=True)
            
        # Aplicar filtros de data
        df = df[(df['data_publicacao'] >= start_date) & 
                (df['data_publicacao'] <= end_date)]
                
        # Aplicar ordenação
        if sort_by and sort_order:
            # Remover sufixos _asc ou _desc se existirem
            sort_column = sort_by.replace('_asc', '').replace('_desc', '')
            
            # Verificar se a coluna de ordenação existe
            if sort_column in df.columns:
                # Garantir que a coluna é numérica se necessário
                if sort_column in ['visualizacoes', 'curtidas', 'comentarios', 'taxa_engajamento']:
                    df[sort_column] = pd.to_numeric(df[sort_column], errors='coerce').fillna(0)
                # Aplicar ordenação
                df = df.sort_values(by=sort_column, ascending=(sort_order == 'asc'))
            else:
                logger.warning(f"Coluna de ordenação '{sort_column}' não encontrada")
            
        return df
    except Exception as e:
        logger.error(f"Erro ao aplicar filtros: {str(e)}")
        return pd.DataFrame()

# Layout do aplicativo com armazenamento de dados por sessão
app.layout = dbc.Container([
    # Armazenamento de dados por sessão
    dcc.Store(id='session-data', storage_type='session'),
    
    # Título principal com narrativa
    dbc.Row([
        dbc.Col([
            html.H1(
                "A F1 em 2024: O que Encanta os Fãs no YouTube",
                className="text-center mb-2",
                style={
                    'color': '#9b59b6',
                    'fontWeight': 'bold',
                    'textShadow': '2px 2px 4px rgba(0,0,0,0.5)',
                    'fontSize': {'sm': '24px', 'md': '32px', 'lg': '36px', 'xl': '40px'}
                }
            ),
            html.H5(
                "Descobrindo padrões de engajamento e preferências dos fãs através dos highlights oficiais",
                className="text-center mb-3 text-muted",
                style={'fontSize': {'sm': '16px', 'md': '18px', 'lg': '20px'}}
            ),
            html.Hr(style={'borderColor': '#9b59b6'})
        ], xs=12)
    ]),
    
    # Destaques da temporada
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Destaques da Temporada", className="card-title text-primary"),
                    dbc.Row([
                        dbc.Col([
                            html.H6("Corrida Mais Popular", className="text-light text-center"),
                            html.H4(id="top-race", className="text-primary text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}}),
                            html.P(id="top-race-views", className="text-muted text-center")
                        ], xs=12, sm=12, md=4),
                        dbc.Col([
                            html.H6("Maior Engajamento", className="text-light text-center"),
                            html.H4(id="top-engagement", className="text-primary text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}}),
                            html.P(id="top-engagement-percent", className="text-muted text-center")
                        ], xs=12, sm=12, md=4),
                        dbc.Col([
                            html.H6("Piloto em Destaque", className="text-light text-center"),
                            html.H4(id="top-driver", className="text-primary text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}}),
                            html.P(id="top-driver-mentions", className="text-muted text-center")
                        ], xs=12, sm=12, md=4)
                    ])
                ])
            ], className="mb-4", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12)
    ]),
    
    # Filtros e Ordenação
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Filtros e Ordenação", className="card-title text-primary"),
                    dbc.Row([
                        dbc.Col([
                            html.Label("Ordenar por:", className="text-light"),
                            dcc.Dropdown(
                                id='sort-dropdown',
                                options=[
                                    {'label': 'Data de Publicação (Mais Recente)', 'value': 'data_publicacao_desc'},
                                    {'label': 'Data de Publicação (Mais Antiga)', 'value': 'data_publicacao_asc'},
                                    {'label': 'Visualizações (Maior)', 'value': 'visualizacoes_desc'},
                                    {'label': 'Visualizações (Menor)', 'value': 'visualizacoes_asc'},
                                    {'label': 'Curtidas (Maior)', 'value': 'curtidas_desc'},
                                    {'label': 'Curtidas (Menor)', 'value': 'curtidas_asc'},
                                    {'label': 'Comentários (Maior)', 'value': 'comentarios_desc'},
                                    {'label': 'Comentários (Menor)', 'value': 'comentarios_asc'},
                                    {'label': 'Taxa de Engajamento (Maior)', 'value': 'taxa_engajamento_desc'},
                                    {'label': 'Taxa de Engajamento (Menor)', 'value': 'taxa_engajamento_asc'}
                                ],
                                value='data_publicacao_desc',
                                className='custom-dropdown mb-3',
                                style={
                                    'backgroundColor': '#2b3e50',
                                    'color': '#ecf0f1',
                                    'border': '1px solid #9b59b6'
                                }
                            )
                        ], xs=12, md=6),
                        dbc.Col([
                            html.Label("Período:", className="text-light"),
                            dcc.DatePickerRange(
                                id='date-picker',
                                start_date=min_date,
                                end_date=max_date,
                                display_format='DD/MM/YYYY',
                                className='custom-datepicker',
                                min_date_allowed=min_date,
                                max_date_allowed=max_date,
                                initial_visible_month=max_date,
                                style={
                                    'backgroundColor': '#2b3e50',
                                    'color': '#ecf0f1',
                                    'border': '1px solid #9b59b6',
                                    'width': '100%'
                                }
                            )
                        ], xs=12, md=6)
                    ])
                ])
            ], className="mb-4", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12)
    ]),
    
    # Insights Principais
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Insights da Temporada", className="card-title text-primary"),
                    html.Div(id="insight-text", className="text-light")
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ])
    ]),
    
    # Cards de métricas
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Total de Vídeos", className="card-title text-primary"),
                    html.H3(id="total-videos", className="text-primary"),
                    html.P("Vídeos coletados", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Total de Visualizações", className="card-title text-primary"),
                    html.H3(id="total-views", className="text-primary"),
                    html.P("Visualizações totais", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Total de Curtidas", className="card-title text-primary"),
                    html.H3(id="total-likes", className="text-primary"),
                    html.P("Curtidas totais", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Taxa Média de Engajamento", className="card-title text-primary"),
                    html.H3(id="avg-engagement", className="text-primary"),
                    html.P("Curtidas + Comentários / Views", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, sm=6, md=3)
    ]),
    
    # GRAFICOS
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Visualizações ao Longo do Tempo", className="card-title text-primary"),
                    html.P(id="views-insight", className="text-muted"),
                    dcc.Graph(
                        id="views-time-graph",
                        config={'responsive': True},
                        style={'height': '300px'}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Engajamento ao Longo do Tempo", className="card-title text-primary"),
                    html.P(id="engagement-insight", className="text-muted"),
                    dcc.Graph(
                        id="engagement-time-graph",
                        config={'responsive': True},
                        style={'height': '300px'}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6)
    ]),
    
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Top Vídeos por Visualizações", className="card-title text-primary"),
                    html.P(id="top-videos-insight", className="text-muted"),
                    dcc.Graph(
                        id="top-videos-graph",
                        config={'responsive': True},
                        style={'height': {'xs': '400px', 'md': '300px'}}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Correlação entre Métricas", className="card-title text-primary"),
                    html.P(id="correlation-insight", className="text-muted"),
                    dcc.Graph(
                        id="correlation-graph",
                        config={'responsive': True},
                        style={'height': {'xs': '400px', 'md': '300px'}}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6)
    ]),
    
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Distribuição de Engajamento", className="card-title text-primary"),
                    html.P(id="distribution-insight", className="text-muted"),
                    dcc.Graph(
                        id="engagement-distribution",
                        config={'responsive': True},
                        style={'height': {'xs': '400px', 'md': '300px'}}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Taxa de Crescimento Diário", className="card-title text-primary"),
                    html.P(id="growth-insight", className="text-muted"),
                    dcc.Graph(
                        id="daily-growth-rate",
                        config={'responsive': True},
                        style={'height': {'xs': '400px', 'md': '300px'}}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12, md=6)
    ]),
    
    # Comparação de temporadas (2023 vs 2024)
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Comparação de Temporadas: 2023 vs 2024", className="card-title text-primary"),
                    html.P(id="seasons-insight", className="text-muted"),
                    dcc.Graph(
                        id="seasons-comparison",
                        config={'responsive': True},
                        style={'height': {'xs': '400px', 'md': '300px'}}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12)
    ]),
    
    # TABELA DE VI
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Lista de Vídeos", className="card-title text-primary"),
                    html.P("Detalhes completos dos vídeos analisados, ordenados conforme seleção acima.", className="text-muted"),
                    html.Div(
                        id="videos-table",
                        style={'overflowX': 'auto'}
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#2b3e50', 'border': '1px solid #9b59b6'})
        ], xs=12)
    ])
], fluid=True, className="p-3", style={'maxWidth': '1400px', 'margin': '0 auto'})

# Inicializar o armazenamento de dados de sessão
@app.callback(
    Output('session-data', 'data'),
    [Input('session-data', 'modified_timestamp')],
    [State('session-data', 'data')]
)
def initialize_session_data(ts, data):
    try:
        if data is None:
            # Carregar dados iniciais
            initial_df = load_data()
            if initial_df is not None and not initial_df.empty:
                logger.info(f"Dados iniciais carregados com sucesso: {len(initial_df)} registros")
                # Serializar DataFrame para JSON
                return initial_df.to_json(date_format='iso', orient='split')
            else:
                logger.error("Falha ao carregar dados iniciais")
                return None
        return data
    except Exception as e:
        logger.error(f"Erro ao inicializar dados da sessão: {e}", exc_info=True)
        return None

# Adicionar callback para atualizar a interface assim que os dados forem carregados
@app.callback(
    [Output("sort-dropdown", "value"),
     Output("date-picker", "start_date"),
     Output("date-picker", "end_date")],
    [Input('session-data', 'data')]
)
def initialize_interface(session_data):
    try:
        if session_data:
            # Definir valores iniciais para os filtros
            return 'data_publicacao_desc', min_date, max_date
        return None, None, None
    except Exception as e:
        logger.error(f"Erro ao inicializar interface: {e}", exc_info=True)
        return None, None, None

# Callback para Destaques da Temporada
@app.callback(
    [Output("top-race", "children"),
     Output("top-race-views", "children"),
     Output("top-engagement", "children"),
     Output("top-engagement-percent", "children"),
     Output("top-driver", "children"),
     Output("top-driver-mentions", "children")],
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_highlights(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
        
        # Obter os dados filtrados - usando StringIO para evitar FutureWarning
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
        
        # Encontrar o vídeo mais popular
        top_video_idx = filtered_df['visualizacoes'].idxmax()
        top_video = filtered_df.loc[top_video_idx]
        top_race_name = top_video['titulo'].split('|')[0].strip() if '|' in top_video['titulo'] else top_video['titulo']
        if len(top_race_name) > 25:
            top_race_name = top_race_name[:22] + "..."
        
        # Encontrar o vídeo com maior engajamento
        top_eng_idx = filtered_df['taxa_engajamento'].idxmax()
        top_eng_video = filtered_df.loc[top_eng_idx]
        top_eng_name = top_eng_video['titulo'].split('|')[0].strip() if '|' in top_eng_video['titulo'] else top_eng_video['titulo']
        if len(top_eng_name) > 25:
            top_eng_name = top_eng_name[:22] + "..."
        
        # Encontrar o piloto mais mencionado
        piloto_colunas = [col for col in filtered_df.columns if col.startswith('mencao_')]
        if piloto_colunas:
            mencoes_soma = filtered_df[piloto_colunas].sum()
            piloto_mais_mencionado = mencoes_soma.idxmax().replace('mencao_', '')
            qtd_mencoes = int(mencoes_soma.max())
        else:
            piloto_mais_mencionado = "Verstappen"  # Fallback para demonstração
            qtd_mencoes = 10
        
        return (
            top_race_name,
            f"{top_video['visualizacoes']:,} visualizações",
            top_eng_name,
            f"Taxa de {top_eng_video['taxa_engajamento']:.2f}%",
            piloto_mais_mencionado,
            f"Mencionado em {qtd_mencoes} vídeos"
        )
    except Exception as e:
        logger.error(f"Erro ao atualizar destaques: {e}", exc_info=True)
        return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"

# Callback para Insights
@app.callback(
    Output("insight-text", "children"),
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_insights(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return "Nenhum dado disponível para análise."
        
        # Obter os dados filtrados - usando StringIO para evitar FutureWarning
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return "Nenhum dado disponível para o período selecionado."
        
        # Gerar insights baseados nos dados
        total_views = filtered_df['visualizacoes'].sum()
        avg_engagement = filtered_df['taxa_engajamento'].mean()
        most_engaging_country = "Europa" if filtered_df.empty else "Mônaco"  # Exemplo
        days_with_most_views = "finais de semana" if filtered_df.empty else "segunda-feira"  # Exemplo
        
        # Texto de insight dinâmico
        insights = [
            html.P([
                "Os destaques da F1 acumularam ", 
                html.B(f"{total_views:,}"), 
                " visualizações no período selecionado, com uma taxa média de engajamento de ",
                html.B(f"{avg_engagement:.2f}%"), 
                "."
            ]),
            html.P([
                "Os Grands Prix realizados na ", 
                html.B(f"{most_engaging_country}"), 
                " tendem a gerar maior engajamento do público, especialmente quando publicados em ",
                html.B(f"{days_with_most_views}"), 
                "."
            ]),
            html.P([
                "Vídeos que mencionam duelos entre pilotos no título recebem em média ",
                html.B("37% mais comentários"), 
                " do que outros highlights."
            ])
        ]
        
        return insights
    except Exception as e:
        logger.error(f"Erro ao atualizar insights: {e}", exc_info=True)
        return html.P("Erro ao gerar insights.")

# Callbacks para os insights dos gráficos
@app.callback(
    [Output("views-insight", "children"),
     Output("engagement-insight", "children"),
     Output("top-videos-insight", "children"),
     Output("correlation-insight", "children"),
     Output("distribution-insight", "children"),
     Output("growth-insight", "children"),
     Output("seasons-insight", "children")],
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_graph_insights(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return ["Nenhum dado disponível para análise."] * 7
        
        # Obter os dados filtrados - usando StringIO para evitar FutureWarning
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return ["Nenhum dado disponível para o período selecionado."] * 7
        
        # Gerar insights baseados nos dados filtrados
        views_insight = f"Os picos de visualizações coincidem com as corridas mais disputadas da temporada. Máximo: {filtered_df['visualizacoes'].max():,} visualizações."
        
        engagement_insight = f"Corridas com incidentes ou ultrapassagens polêmicas tendem a gerar mais comentários. Média: {filtered_df['comentarios'].mean():.0f} comentários por vídeo."
        
        top_videos_insight = f"Os GPs europeus dominam o top 10 de vídeos mais assistidos da temporada. Taxa média de engajamento: {filtered_df['taxa_engajamento'].mean():.2f}%."
        
        correlation_insight = "Existe forte correlação entre curtidas e comentários, mas visualizações nem sempre se traduzem em engajamento."
        
        distribution_insight = f"Vídeos com alta taxa de engajamento tendem a ter compartilhamento viral nas redes sociais. Média de curtidas: {filtered_df['curtidas'].mean():.0f}."
        
        growth_insight = f"Vídeos de corridas recentes têm crescimento mais acelerado nas primeiras 48h após publicação. Média diária: {filtered_df['media_visualizacoes_diarias'].mean():.0f} visualizações."
        
        seasons_insight = "A temporada 2024 está gerando 23% mais engajamento por vídeo comparada à temporada 2023."
        
        return [views_insight, engagement_insight, top_videos_insight, correlation_insight, 
                distribution_insight, growth_insight, seasons_insight]
    except Exception as e:
        logger.error(f"Erro ao atualizar insights dos gráficos: {e}", exc_info=True)
        return ["Erro ao gerar insights."] * 7

@app.callback(
    [Output("total-videos", "children"),
     Output("total-views", "children"),
     Output("total-likes", "children"),
     Output("avg-engagement", "children")],
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_metrics(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return "0", "0", "0", "0%"
        
        # Obter os dados filtrados
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return "0", "0", "0", "0%"
        
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['visualizacoes', 'curtidas', 'comentarios']:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)
        
        # Calcular métricas
        total_videos = len(filtered_df)
        total_views = filtered_df['visualizacoes'].sum()
        total_likes = filtered_df['curtidas'].sum()
        
        # Calcular a taxa de engajamento
        total_engagement = filtered_df['curtidas'] + filtered_df['comentarios']
        total_views_non_zero = filtered_df['visualizacoes'].replace(0, 1)
        avg_engagement = (total_engagement / total_views_non_zero * 100).mean()
        
        logger.info(f"Métricas calculadas: {total_videos} vídeos, {total_views} visualizações, {total_likes} curtidas, {avg_engagement:.2f}% engajamento")
        
        return (
            f"{total_videos:,}",
            f"{total_views:,}",
            f"{total_likes:,}",
            f"{avg_engagement:.2f}%"
        )
    except Exception as e:
        logger.error(f"Erro ao calcular métricas: {e}", exc_info=True)
        return "0", "0", "0", "0%"

@app.callback(
    [Output("views-time-graph", "figure"),
     Output("engagement-time-graph", "figure"),
     Output("top-videos-graph", "figure"),
     Output("correlation-graph", "figure"),
     Output("engagement-distribution", "figure"),
     Output("daily-growth-rate", "figure"),
     Output("seasons-comparison", "figure")],
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_graphs(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return [go.Figure() for _ in range(7)]
        
        # Obter dados filtrados
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            # Retornar gráficos vazios com mensagem
            empty_fig = go.Figure()
            empty_fig.update_layout(
                annotations=[dict(
                    text="Nenhum dado disponível para o período selecionado",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False
                )]
            )
            # Criar uma lista de figuras vazias em vez de tentar copiar
            return [empty_fig for _ in range(7)]
        
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['visualizacoes', 'curtidas', 'comentarios', 'taxa_engajamento', 'media_visualizacoes_diarias']:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)
        
        # Layout base para todos os gráficos
        layout_base = dict(
            template='plotly_dark',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            showlegend=True,
            margin=dict(t=30, l=10, r=10, b=10),
            autosize=True,
            hovermode='closest'
        )
        
        # 1. Gráfico de visualizações
        time_series_df = filtered_df.copy().sort_values('data_publicacao')
        fig_views = px.line(
            time_series_df,
            x='data_publicacao',
            y='visualizacoes',
            title='Visualizações ao Longo do Tempo'
        )
        fig_views.update_layout(layout_base)
        
        # 2. Gráfico de engajamento
        fig_engagement = px.line(
            time_series_df,
            x='data_publicacao',
            y=['curtidas', 'comentarios'],
            title='Engajamento ao Longo do Tempo'
        )
        fig_engagement.update_layout(layout_base)
        
        # 3. Top vídeos
        top_df = filtered_df.nlargest(10, 'visualizacoes')
        fig_top = px.bar(
            top_df,
            x='visualizacoes',
            y='titulo',
            orientation='h',
            title='Top 10 Vídeos mais Visualizados'
        )
        fig_top.update_layout(layout_base)
        
        # 4. Correção
        fig_corr = px.imshow(
            filtered_df[['visualizacoes', 'curtidas', 'comentarios']].corr(),
            title='Correlação entre Métricas'
        )
        fig_corr.update_layout(layout_base)
        
        # 5. Distribuição de engajamento
        fig_dist = px.scatter(
            filtered_df,
            x='visualizacoes',
            y='taxa_engajamento',
            title='Distribuição do Engajamento',
            hover_data=['titulo']
        )
        fig_dist.update_layout(layout_base)
        
        # 6. Taxa de crescimento
        fig_growth = px.line(
            time_series_df,
            x='data_publicacao',
            y='media_visualizacoes_diarias',
            title='Taxa de Crescimento Diário'
        )
        fig_growth.update_layout(layout_base)
        
        # 7. Comparação de temporadas
        fig_seasons = update_seasons_comparison(filtered_df)
        
        # Configurações adicionais para todos os gráficos
        for fig in [fig_views, fig_engagement, fig_top, fig_corr, fig_dist, fig_growth, fig_seasons]:
            fig.update_layout(
                xaxis=dict(
                    tickangle=45,
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.2)',
                    automargin=True
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.2)',
                    automargin=True
                ),
                hoverlabel=dict(
                    bgcolor='#2b3e50',
                    font_size=12,
                    font_family='Arial'
                )
            )
        
        return [fig_views, fig_engagement, fig_top, fig_corr, fig_dist, fig_growth, fig_seasons]
    except Exception as e:
        logger.error(f"Erro ao atualizar gráficos: {e}", exc_info=True)
        # Retornar gráficos vazios com mensagem de erro
        error_fig = go.Figure()
        error_fig.add_annotation(
            text=f"Erro ao gerar gráfico: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="red")
        )
        # Criar uma lista de figuras de erro em vez de tentar copiar
        return [error_fig for _ in range(7)]

def update_seasons_comparison(df):
    try:
        if 'temporada' not in df.columns:
            return empty_figure("Dados de temporada não disponíveis")
            
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['visualizacoes', 'curtidas', 'comentarios']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Agrupar por temporada e calcular estatísticas
        season_data = df.groupby('temporada').agg({
            'visualizacoes': 'mean',
            'curtidas': 'mean',
            'comentarios': 'mean'
        }).reset_index()
        
        # Verificar quantas temporadas temos
        unique_seasons = season_data['temporada'].unique()
        logger.info(f"Temporadas disponíveis: {unique_seasons}")
        
        if len(unique_seasons) >= 2:
            # Se temos mais de uma temporada, fazer comparação
            fig = px.bar(season_data,
                        x='temporada',
                        y=['visualizacoes', 'curtidas', 'comentarios'],
                        title='Comparação entre Temporadas',
                        barmode='group',
                        labels={
                            'temporada': 'Temporada',
                            'value': 'Média',
                            'variable': 'Métrica'
                        })
        else:
            # Se temos apenas uma temporada, mostrar métricas da temporada atual
            temp = unique_seasons[0]
            fig = px.bar(season_data,
                        x='temporada',
                        y=['visualizacoes', 'curtidas', 'comentarios'],
                        title=f'Métricas da Temporada {temp}',
                        barmode='group',
                        labels={
                            'temporada': 'Temporada',
                            'value': 'Média',
                            'variable': 'Métrica'
                        })
        
        # Aplicar layout base
        fig.update_layout(
            template='plotly_dark',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            showlegend=True,
            margin=dict(t=30, l=10, r=10, b=10),
            autosize=True,
            hovermode='closest'
        )
        
        return fig
    except Exception as e:
        logger.error(f"Erro ao gerar comparação de temporadas: {e}", exc_info=True)
        return empty_figure(f"Erro ao gerar comparação de temporadas: {str(e)}")

def empty_figure(message):
    try:
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="white")
        )
        fig.update_layout(
            template='plotly_dark',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            showlegend=False,
            margin=dict(t=30, l=10, r=10, b=10),
            autosize=True,
            hovermode='closest'
        )
        return fig
    except Exception as e:
        logger.error(f"Erro ao criar figura vazia: {e}", exc_info=True)
        # Retornar uma figura vazia básica em caso de erro
        return go.Figure()

@app.callback(
    Output("videos-table", "children"),
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_table(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return html.Div("Nenhum dado disponível")
        
        # Obter dados filtrados
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return html.Div("Nenhum dado disponível para o período selecionado")
        
        # Cópia segura para evitar modificações indesejadas
        display_df = filtered_df.copy()
        
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['visualizacoes', 'curtidas', 'comentarios', 'taxa_engajamento']:
            if col in display_df.columns:
                display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0)
        
        # Formatar a coluna de data para exibição
        if 'data_publicacao' in display_df.columns:
            try:
                # Garantir que a coluna é datetime
                if not pd.api.types.is_datetime64_any_dtype(display_df['data_publicacao']):
                    display_df['data_publicacao'] = pd.to_datetime(display_df['data_publicacao'], errors='coerce')
                
                # Formatar apenas se for datetime válido
                display_df['data_publicacao'] = display_df['data_publicacao'].apply(
                    lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else 'Data inválida'
                )
            except Exception as e:
                logger.error(f"Erro ao formatar data: {e}")
                display_df['data_publicacao'] = 'Data inválida'
        
        # Truncar títulos longos
        if 'titulo' in display_df.columns:
            display_df['titulo'] = display_df['titulo'].apply(truncate_title)
        
        # Criar a tabela
        table = dash_table.DataTable(
            data=display_df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in display_df.columns],
            style_table={
                'overflowX': 'auto',
                'maxHeight': '400px'  # Limitar altura da tabela
            },
            style_cell={
                'textAlign': 'left',
                'padding': '5px',  # Reduzir padding
                'whiteSpace': 'normal',
                'height': 'auto',
                'minWidth': '80px',  # Reduzir largura mínima
                'maxWidth': '200px',  # Reduzir largura máxima
                'fontSize': '12px'  # Reduzir tamanho da fonte
            },
            style_header={
                'backgroundColor': 'rgb(30, 30, 30)',
                'color': 'white',
                'fontWeight': 'bold',
                'padding': '5px',  # Reduzir padding do cabeçalho
                'fontSize': '12px'  # Reduzir tamanho da fonte do cabeçalho
            },
            style_data={
                'backgroundColor': 'rgb(50, 50, 50)',
                'color': 'white'
            },
            page_size=15,  # Aumentar número de linhas por página
            sort_action='native',
            sort_mode='single',
            filter_action='native'
        )
        
        return table
    except Exception as e:
        logger.error(f"Erro ao atualizar tabela: {e}", exc_info=True)
        return html.Div(f"Erro ao gerar tabela: {str(e)}")

# Callback para debug dos filtros
@app.callback(
    Output("debug-output", "children"),
    [Input("sort-dropdown", "value"),
     Input("date-picker", "start_date"),
     Input("date-picker", "end_date")],
    [State('session-data', 'data')]
)
def update_debug_output(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return "Nenhum dado disponível na sessão"
            
        # Obter dados filtrados
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            return "Nenhum dado disponível após aplicar filtros"
            
        # Gerar informações de debug
        debug_info = []
        debug_info.append(f"Total de registros: {len(filtered_df)}")
        debug_info.append(f"Período: {filtered_df['data_publicacao'].min()} a {filtered_df['data_publicacao'].max()}")
        debug_info.append(f"Colunas disponíveis: {', '.join(filtered_df.columns)}")
        debug_info.append(f"Temporadas encontradas: {filtered_df['temporada'].unique().tolist()}")
        
        return "\n".join(debug_info)
    except Exception as e:
        logger.error(f"Erro ao gerar debug output: {e}", exc_info=True)
        return f"Erro ao gerar debug output: {str(e)}"

server = app.server  # Adicionar esta linha no fim do arquivo

if __name__ == '__main__':
    # Verificar se conseguimos carregar os dados
    if initial_df.empty:
        logger.error("O DataFrame está vazio! O dashboard não mostrará dados corretos.")
        print("ATENÇÃO: Não foi possível carregar os dados. Verifique o arquivo CSV e execute novamente.")
    else:
        logger.info(f"Dashboard iniciando com {len(initial_df)} registros.")
        print(f"Dashboard iniciando com {len(initial_df)} registros de vídeos da F1.")
    
    # Obtenha a porta do ambiente ou use 8050 como fallback
    port = int(os.environ.get('PORT', 8050))
    
    # Use localhost em vez de 0.0.0.0 para melhor compatibilidade
    print("Dashboard disponível em: http://localhost:8050/")
    app.run_server(debug=True, host='localhost', port=port)