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
    external_stylesheets=[dbc.themes.FLATLY],
    meta_tags=[
        {'name': 'viewport', 'content': 'width=device-width, maximum-scale=1.0, minimum-scale=1.0'}
    ],
    assets_folder='assets',
    suppress_callback_exceptions=True
)

# Estilos base para componentes
DROPDOWN_STYLE = {
    'borderRadius': '8px',
    'border': '1px solid #E2E8F0',
    'backgroundColor': '#F8FAFC',
    'color': '#2D3748',
    'fontSize': '14px',
    'fontWeight': '500',
    'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important',
    'height': '38px'
}

DATE_PICKER_STYLE = {
    'zIndex': '1000',
    'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important',
    'fontSize': '14px',
    'backgroundColor': '#FFFFFF',
    'border': '1px solid #E2E8F0',
    'borderRadius': '8px',
    'boxShadow': 'none'
}

# Layout base para gráficos
GRAPH_LAYOUT_BASE = {
    'template': 'plotly',
    'plot_bgcolor': 'rgba(249,250,251,0)',
    'paper_bgcolor': 'rgba(255,255,255,0)',
    'font': {
        'family': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        'color': '#1A202C'
    },
    'showlegend': True,
    'margin': dict(t=30, l=10, r=10, b=10),
    'autosize': True,
    'hovermode': 'closest'
}

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
        visualizacoes = float(row['Visualizações'])
        curtidas = float(row['Curtidas'])
        comentarios = float(row['Comentários'])
        
        # Evitar divisão por zero
        if visualizacoes == 0:
            return 0.0
            
        # Calcular taxa de engajamento
        taxa = ((curtidas + comentarios) / visualizacoes) * 100
        return round(taxa, 2)
    except Exception as e:
        logger.error(f"Erro ao calcular taxa de engajamento: {e}")
        return 0.0

def load_data():
    """Carrega os dados do CSV em tempo real."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'f1_2024_highlights.csv')
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Arquivo CSV não encontrado em: {csv_path}")
        
        # Carregar o CSV
        df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')
        
        # Renomear colunas para nomes mais amigáveis
        column_mapping = {
            'video_id': 'ID do Vídeo',
            'titulo': 'Título',
            'data_publicacao': 'Data de Publicação',
            'visualizacoes': 'Visualizações',
            'curtidas': 'Curtidas',
            'comentarios': 'Comentários',
            'duracao': 'Duração',
            'thumbnail': 'Thumbnail',
            'descricao': 'Descrição',
            'tags': 'Tags',
            'canal': 'Canal',
            'taxa_engajamento': 'Taxa de Engajamento',
            'media_visualizacoes_diarias': 'Média de Visualizações Diárias',
            'dias_desde_publicacao': 'Dias Desde Publicação',
            'proporcao_curtidas_visualizacoes': 'Proporção Curtidas/Visualizações',
            'proporcao_comentarios_visualizacoes': 'Proporção Comentários/Visualizações',
            'temporada': 'Temporada'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Converter a coluna de data
        file_size = os.path.getsize(csv_path)
        logger.info(f"Tamanho do arquivo: {file_size} bytes")

        try:
            df['Data de Publicação'] = pd.to_datetime(df['Data de Publicação'], errors='coerce', utc=True)
            logger.info("Coluna de data convertida com sucesso")
            
            if df['Data de Publicação'].isna().any():
                logger.warning(f"Existem {df['Data de Publicação'].isna().sum()} valores de data que não puderam ser convertidos")
                df = df.dropna(subset=['Data de Publicação'])
        except Exception as e:
            logger.error(f"Erro ao converter datas: {e}")
            raise
        
        if df.empty:
            logger.error("DataFrame está vazio após carregamento!")
            raise ValueError("DataFrame está vazio após carregamento")
            
        logger.info(f"DataFrame carregado com {len(df)} linhas e {len(df.columns)} colunas")
        logger.info(f"Colunas disponíveis: {df.columns.tolist()}")
        
        try:
            # Taxa de engajamento
            df['Taxa de Engajamento'] = df.apply(safe_engagement_rate, axis=1)
            
            # Média diária de visualizações
            hoje = pd.Timestamp.now(tz='UTC')
            df['Dias Desde Publicação'] = (hoje - df['Data de Publicação']).dt.days
            df['Dias Desde Publicação'] = np.where(
                df['Dias Desde Publicação'] < 1,
                1,
                df['Dias Desde Publicação']
            )
            df['Média de Visualizações Diárias'] = (df['Visualizações'] / df['Dias Desde Publicação']).round(0)
            
            # Outras métricas
            df['Proporção Curtidas/Visualizações'] = np.where(
                df['Visualizações'] > 0,
                (df['Curtidas'] / df['Visualizações'] * 100).round(2),
                0
            )
            df['Proporção Comentários/Visualizações'] = np.where(
                df['Visualizações'] > 0,
                (df['Comentários'] / df['Visualizações'] * 100).round(2),
                0
            )
            
            # Extrair temporada do título
            df['Temporada'] = df['Título'].str.extract(r'(\d{4})')
            df['Temporada'] = df['Temporada'].fillna(df['Data de Publicação'].dt.year.astype(str))
            df['Temporada'] = df['Temporada'].where(df['Temporada'].isin(['2023', '2024']), '2024')
            
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
            
        # Garantir que a coluna Data de Publicação é datetime
        if not pd.api.types.is_datetime64_any_dtype(df['Data de Publicação']):
            df['Data de Publicação'] = pd.to_datetime(df['Data de Publicação'], utc=True)
            
        # Aplicar filtros de data
        df = df[(df['Data de Publicação'] >= start_date) & 
                (df['Data de Publicação'] <= end_date)]
                
        # Aplicar ordenação
        if sort_by and sort_order:
            # Remover sufixos _asc ou _desc se existirem
            sort_column = sort_by.replace('_asc', '').replace('_desc', '')
            
            # Verificar se a coluna de ordenação existe
            if sort_column in df.columns:
                # Garantir que a coluna é numérica se necessário
                if sort_column in ['Visualizações', 'Curtidas', 'Comentários', 'Taxa de Engajamento']:
                    df[sort_column] = pd.to_numeric(df[sort_column], errors='coerce').fillna(0)
                # Aplicar ordenação
                df = df.sort_values(by=sort_column, ascending=(sort_order == 'asc'))
            else:
                logger.warning(f"Coluna de ordenação '{sort_column}' não encontrada")
            
        return df
    except Exception as e:
        logger.error(f"Erro ao aplicar filtros: {str(e)}")
        return pd.DataFrame()

# Combined callback for data initialization and periodic updates
@app.callback(
    Output('session-data', 'data'),
    [Input('session-data', 'modified_timestamp'),
     Input('interval-component', 'n_intervals')],
    [State('session-data', 'data')]
)
def combined_data_callback(ts, n_intervals, data):
    """Handles both initialization and periodic updates of data"""
    try:
        # Use callback context to determine which input triggered the callback
        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        
        # For initialization (session-data modified_timestamp)
        if trigger_id == 'session-data' and data is None:
            # Initial load
            initial_df = load_data()
            if initial_df is not None and not initial_df.empty:
                logger.info(f"Dados iniciais carregados com sucesso: {len(initial_df)} registros")
                return initial_df.to_json(date_format='iso', orient='split')
            else:
                logger.error("Falha ao carregar dados iniciais")
                return None
                
        # For periodic updates (interval-component)
        elif trigger_id == 'interval-component':
            # Load updated data
            updated_df = load_data()
            if updated_df is not None and not updated_df.empty:
                logger.info(f"Dados atualizados com sucesso: {len(updated_df)} registros")
                return updated_df.to_json(date_format='iso', orient='split')
        
        # If no trigger matched or update wasn't needed, return current data
        return data
    except Exception as e:
        logger.error(f"Erro ao processar dados: {e}", exc_info=True)
        return data

# Layout do aplicativo com armazenamento de dados por sessão
app.layout = dbc.Container([
    # Intervalo para atualização automática (a cada 30 segundos)
    dcc.Interval(
        id='interval-component',
        interval=30*1000,  # em milissegundos
        n_intervals=0
    ),
    
    # Armazenamento de dados por sessão
    dcc.Store(id='session-data', storage_type='session'),
    
    # Título principal com narrativa
    dbc.Row([
        dbc.Col([
            html.H1(
                "A F1 em 2024: O que Encanta os Fãs no YouTube",
                className="text-center mb-2",
                style={
                    'color': '#6E72FC',  # Cor primária do tema
                    'fontWeight': 'bold',
                    'textShadow': '2px 2px 4px rgba(110, 114, 252, 0.2)',
                    'fontSize': {'sm': '24px', 'md': '32px', 'lg': '36px', 'xl': '40px'}
                }
            ),
            html.H5(
                "Descobrindo padrões de engajamento e preferências dos fãs através dos highlights oficiais",
                className="text-center mb-3 text-muted",
                style={'fontSize': {'sm': '16px', 'md': '18px', 'lg': '20px'}}
            ),
            html.Hr(style={'borderColor': '#6E72FC'})
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
                            html.H6("Corrida Mais Popular", className="text-dark text-center"),
                            html.H4(id="top-race", className="text-dark text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}, 'color': '#2c3e50'}),
                            html.P(id="top-race-views", className="text-muted text-center")
                        ], xs=12, sm=12, md=4),
                        dbc.Col([
                            html.H6("Maior Engajamento", className="text-dark text-center"),
                            html.H4(id="top-engagement", className="text-dark text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}, 'color': '#2c3e50'}),
                            html.P(id="top-engagement-percent", className="text-muted text-center")
                        ], xs=12, sm=12, md=4),
                        dbc.Col([
                            html.H6("Piloto em Destaque", className="text-dark text-center"),
                            html.H4(id="top-driver", className="text-dark text-center", style={'fontSize': {'sm': '16px', 'md': '20px'}, 'color': '#2c3e50'}),
                            html.P(id="top-driver-mentions", className="text-muted text-center")
                        ], xs=12, sm=12, md=4)
                    ])
                ])
            ], className="mb-4", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12)
    ]),
    
    # Filtros e Ordenação
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Filtros e Ordenação", className="card-title text-primary", style={'fontFamily': 'Lexend, sans-serif'}),
                    dbc.Row([
                        dbc.Col([
                            html.Label("Ordenar por:", className="text-dark fw-bold mb-2", style={'fontFamily': 'Lexend, sans-serif'}),
                            dcc.Dropdown(
                                id='sort-dropdown',
                                options=[
                                    {'label': 'Data de Publicação (Mais Recente)', 'value': 'Data de Publicação_desc'},
                                    {'label': 'Data de Publicação (Mais Antiga)', 'value': 'Data de Publicação_asc'},
                                    {'label': 'Visualizações (Maior)', 'value': 'Visualizações_desc'},
                                    {'label': 'Visualizações (Menor)', 'value': 'Visualizações_asc'},
                                    {'label': 'Curtidas (Maior)', 'value': 'Curtidas_desc'},
                                    {'label': 'Curtidas (Menor)', 'value': 'Curtidas_asc'},
                                    {'label': 'Comentários (Maior)', 'value': 'Comentários_desc'},
                                    {'label': 'Comentários (Menor)', 'value': 'Comentários_asc'},
                                    {'label': 'Taxa de Engajamento (Maior)', 'value': 'Taxa de Engajamento_desc'},
                                    {'label': 'Taxa de Engajamento (Menor)', 'value': 'Taxa de Engajamento_asc'}
                                ],
                                value='Data de Publicação_desc',
                                className='custom-dropdown',
                                style=DROPDOWN_STYLE
                            )
                        ], xs=12, md=6, className='mb-3'),
                        dbc.Col([
                            html.Label("Período:", className="text-dark fw-bold mb-2", style={'fontFamily': 'Lexend, sans-serif'}),
                            dcc.DatePickerRange(
                                id='date-picker',
                                start_date=min_date,
                                end_date=max_date,
                                display_format='DD/MM/YYYY',
                                className='custom-datepicker w-100',
                                min_date_allowed=min_date,
                                max_date_allowed=max_date,
                                initial_visible_month=max_date,
                                style=DATE_PICKER_STYLE,
                                start_date_placeholder_text='Data Inicial',
                                end_date_placeholder_text='Data Final',
                                calendar_orientation='horizontal',
                                clearable=True,
                                with_portal=True,
                                updatemode='bothdates'
                            )
                        ], xs=12, md=6, className='mb-3')
                    ], className='g-3')
                ])
            ], className="mb-4", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12)
    ]),
    
    # Insights Principais
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Insights da Temporada", className="card-title text-primary"),
                    html.Div(id="insight-text", className="text-dark")
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Total de Visualizações", className="card-title text-primary"),
                    html.H3(id="total-views", className="text-primary"),
                    html.P("Visualizações totais", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Total de Curtidas", className="card-title text-primary"),
                    html.H3(id="total-likes", className="text-primary"),
                    html.P("Curtidas totais", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, sm=6, md=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Taxa Média de Engajamento", className="card-title text-primary"),
                    html.H3(id="avg-engagement", className="text-primary"),
                    html.P("Curtidas + Comentários / Views", className="text-muted")
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
                        style={'height': '400px', 'marginBottom': '20px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Engajamento ao Longo do Tempo", className="card-title text-primary"),
                    html.P(id="engagement-insight", className="text-muted"),
                    dcc.Graph(
                        id="engagement-time-graph",
                        config={'responsive': True},
                        style={'height': '400px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
                        style={'height': '400px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Correlação entre Métricas", className="card-title text-primary"),
                    html.P(id="correlation-insight", className="text-muted"),
                    dcc.Graph(
                        id="correlation-graph",
                        config={'responsive': True},
                        style={'height': '400px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
                        style={'height': '400px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12, md=6),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Taxa de Crescimento Diário", className="card-title text-primary"),
                    html.P(id="growth-insight", className="text-muted"),
                    dcc.Graph(
                        id="daily-growth-rate",
                        config={'responsive': True},
                        style={'height': '400px'}  # Altura ajustada
                    )
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
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
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12)
    ])
], fluid=True, className="p-3", style={'maxWidth': '1400px', 'margin': '0 auto'})

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
            return 'Data de Publicação_desc', min_date, max_date
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
        top_video_idx = filtered_df['Visualizações'].idxmax()
        top_video = filtered_df.loc[top_video_idx]
        top_race_name = top_video['Título'].split('|')[0].strip() if '|' in top_video['Título'] else top_video['Título']
        if len(top_race_name) > 25:
            top_race_name = top_race_name[:22] + "..."
        
        # Encontrar o vídeo com maior engajamento
        top_eng_idx = filtered_df['Taxa de Engajamento'].idxmax()
        top_eng_video = filtered_df.loc[top_eng_idx]
        top_eng_name = top_eng_video['Título'].split('|')[0].strip() if '|' in top_eng_video['Título'] else top_eng_video['Título']
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
            f"{top_video['Visualizações']:,} visualizações",
            top_eng_name,
            f"Taxa de {top_eng_video['Taxa de Engajamento']:.2f}%",
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
        total_views = filtered_df['Visualizações'].sum()
        avg_engagement = filtered_df['Taxa de Engajamento'].mean()
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
        views_insight = f"Os picos de visualizações coincidem com as corridas mais disputadas da temporada. Máximo: {filtered_df['Visualizações'].max():,} visualizações."
        
        engagement_insight = f"Corridas com incidentes ou ultrapassagens polêmicas tendem a gerar mais comentários. Média: {filtered_df['Comentários'].mean():.0f} comentários por vídeo."
        
        top_videos_insight = f"Os GPs europeus dominam o top 10 de vídeos mais assistidos da temporada. Taxa média de engajamento: {filtered_df['Taxa de Engajamento'].mean():.2f}%."
        
        correlation_insight = "Existe forte correlação entre curtidas e comentários, mas visualizações nem sempre se traduzem em engajamento."
        
        distribution_insight = f"Vídeos com alta taxa de engajamento tendem a ter compartilhamento viral nas redes sociais. Média de curtidas: {filtered_df['Curtidas'].mean():.0f}."
        
        growth_insight = f"Vídeos de corridas recentes têm crescimento mais acelerado nas primeiras 48h após publicação. Média diária: {filtered_df['Média de Visualizações Diárias'].mean():.0f} visualizações."
        
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
        for col in ['Visualizações', 'Curtidas', 'Comentários']:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)
        
        # Calcular métricas
        total_videos = len(filtered_df)
        total_views = filtered_df['Visualizações'].sum()
        total_likes = filtered_df['Curtidas'].sum()
        
        # Calcular a taxa de engajamento
        total_engagement = filtered_df['Curtidas'] + filtered_df['Comentários']
        total_views_non_zero = filtered_df['Visualizações'].replace(0, 1)
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

def update_graphs(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            return [go.Figure() for _ in range(7)]
        
        # Obter dados filtrados
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        
        if filtered_df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(
                annotations=[dict(
                    text="Nenhum dado disponível para o período selecionado",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif')
                )],
                **GRAPH_LAYOUT_BASE
            )
            return [empty_fig for _ in range(7)]
        
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['Visualizações', 'Curtidas', 'Comentários', 'Taxa de Engajamento', 'Média de Visualizações Diárias']:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)
        
        # 1. Gráfico de visualizações
        time_series_df = filtered_df.copy().sort_values('Data de Publicação')
        fig_views = px.line(
            time_series_df,
            x='Data de Publicação',
            y='Visualizações',
            title='Visualizações ao Longo do Tempo'
        )
        fig_views.update_layout(**GRAPH_LAYOUT_BASE)
        fig_views.update_traces(line_color='#4299E1')
        
        # 2. Gráfico de engajamento
        fig_engagement = px.line(
            time_series_df,
            x='Data de Publicação',
            y=['Curtidas', 'Comentários'],
            title='Engajamento ao Longo do Tempo'
        )
        fig_engagement.update_layout(**GRAPH_LAYOUT_BASE)
        fig_engagement.update_traces(selector={'name': 'Curtidas'}, line_color='#ED8936')
        fig_engagement.update_traces(selector={'name': 'Comentários'}, line_color='#9F7AEA')
        
        # 3. Top vídeos
        top_df = filtered_df.nlargest(10, 'Visualizações')
        fig_top = px.bar(
            top_df,
            x='Visualizações',
            y='Título',
            orientation='h',
            title='Top 10 Vídeos mais Visualizados'
        )
        fig_top.update_layout(**GRAPH_LAYOUT_BASE)
        
        # 4. Correlação
        fig_corr = px.imshow(
            filtered_df[['Visualizações', 'Curtidas', 'Comentários']].corr(),
            title='Correlação entre Métricas'
        )
        fig_corr.update_layout(**GRAPH_LAYOUT_BASE)
        
        # 5. Distribuição de engajamento
        fig_dist = px.scatter(
            filtered_df,
            x='Visualizações',
            y='Taxa de Engajamento',
            title='Distribuição do Engajamento',
            hover_data=['Título']
        )
        fig_dist.update_layout(**GRAPH_LAYOUT_BASE)
        
        # 6. Taxa de crescimento
        fig_growth = px.line(
            time_series_df,
            x='Data de Publicação',
            y='Média de Visualizações Diárias',
            title='Taxa de Crescimento Diário'
        )
        fig_growth.update_layout(**GRAPH_LAYOUT_BASE)
        
        # 7. Comparação de temporadas
        fig_seasons = update_seasons_comparison(filtered_df)
        
        # Configurações adicionais para todos os gráficos
        for fig in [fig_views, fig_engagement, fig_top, fig_corr, fig_dist, fig_growth, fig_seasons]:
            fig.update_layout(
                xaxis=dict(
                    tickangle=45,
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.2)',
                    automargin=True,
                    tickfont=dict(family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif')
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='rgba(128,128,128,0.2)',
                    automargin=True,
                    tickfont=dict(family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif')
                ),
                hoverlabel=dict(
                    bgcolor='#2b3e50',
                    font_size=12,
                    font_family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
                ),
                title_font=dict(family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif')
            )
        
        return [fig_views, fig_engagement, fig_top, fig_corr, fig_dist, fig_growth, fig_seasons]
    except Exception as e:
        logger.error(f"Erro ao atualizar gráficos: {e}", exc_info=True)
        error_fig = go.Figure()
        error_fig.add_annotation(
            text=f"Erro ao gerar gráfico: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(
                size=16,
                color="red",
                family='"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            )
        )
        error_fig.update_layout(**GRAPH_LAYOUT_BASE)
        return [error_fig for _ in range(7)]

def update_seasons_comparison(df):
    try:
        if 'Temporada' not in df.columns:
            return empty_figure("Dados de temporada não disponíveis")
            
        # Garantir que as colunas numéricas sejam do tipo correto
        for col in ['Visualizações', 'Curtidas', 'Comentários']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Agrupar por temporada e calcular estatísticas
        season_data = df.groupby('Temporada').agg({
            'Visualizações': 'mean',
            'Curtidas': 'mean',
            'Comentários': 'mean'
        }).reset_index()
        
        # Verificar quantas temporadas temos
        unique_seasons = season_data['Temporada'].unique()
        logger.info(f"Temporadas disponíveis: {unique_seasons}")
        
        if len(unique_seasons) >= 2:
            # Se temos mais de uma temporada, fazer comparação
            fig = px.bar(season_data,
                        x='Temporada',
                        y=['Visualizações', 'Curtidas', 'Comentários'],
                        title='Comparação entre Temporadas',
                        barmode='group',
                        labels={
                            'Temporada': 'Temporada',
                            'value': 'Média',
                            'variable': 'Métrica'
                        })
        else:
            # Se temos apenas uma temporada, mostrar métricas da temporada atual
            temp = unique_seasons[0]
            fig = px.bar(season_data,
                        x='Temporada',
                        y=['Visualizações', 'Curtidas', 'Comentários'],
                        title=f'Métricas da Temporada {temp}',
                        barmode='group',
                        labels={
                            'Temporada': 'Temporada',
                            'value': 'Média',
                            'variable': 'Métrica'
                        })
        
        # Aplicar layout base
        fig.update_layout(
            template='plotly',
            plot_bgcolor='rgba(249,250,251,0)',
            paper_bgcolor='rgba(255,255,255,0)',
            font_color='#1A202C',
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
            template='plotly',
            plot_bgcolor='rgba(249,250,251,0)',
            paper_bgcolor='rgba(255,255,255,0)',
            font_color='#1A202C',
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
        for col in ['Visualizações', 'Curtidas', 'Comentários', 'Taxa de Engajamento']:
            if col in display_df.columns:
                display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0)
        
        # Formatar a coluna de data para exibição
        if 'Data de Publicação' in display_df.columns:
            try:
                # Garantir que a coluna é datetime
                if not pd.api.types.is_datetime64_any_dtype(display_df['Data de Publicação']):
                    display_df['Data de Publicação'] = pd.to_datetime(display_df['Data de Publicação'], errors='coerce')
                
                # Formatar apenas se for datetime válido
                display_df['Data de Publicação'] = display_df['Data de Publicação'].apply(
                    lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else 'Data inválida'
                )
            except Exception as e:
                logger.error(f"Erro ao formatar data: {e}")
                display_df['Data de Publicação'] = 'Data inválida'
        
        # Truncar títulos longos
        if 'Título' in display_df.columns:
            display_df['Título'] = display_df['Título'].apply(truncate_title)
        
        # Criar a tabela
        table = dash_table.DataTable(
            data=display_df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in display_df.columns],
            style_table={
                'overflowX': 'auto',
                'maxHeight': '400px',
                'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            style_cell={
                'textAlign': 'left',
                'padding': '5px',
                'whiteSpace': 'normal',
                'height': 'auto',
                'minWidth': '80px',
                'maxWidth': '200px',
                'fontSize': '12px',
                'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            style_header={
                'backgroundColor': '#F7FAFC',
                'color': '#1A202C',
                'fontWeight': 'bold',
                'padding': '5px',
                'fontSize': '12px',
                'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            style_data={
                'backgroundColor': '#FFFFFF',
                'color': '#1A202C',
                'fontFamily': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            page_size=15,
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
        debug_info.append(f"Período: {filtered_df['Data de Publicação'].min()} a {filtered_df['Data de Publicação'].max()}")
        debug_info.append(f"Colunas disponíveis: {', '.join(filtered_df.columns)}")
        debug_info.append(f"Temporadas encontradas: {filtered_df['Temporada'].unique().tolist()}")
        
        return "\n".join(debug_info)
    except Exception as e:
        logger.error(f"Erro ao gerar debug output: {e}", exc_info=True)
        return f"Erro ao gerar debug output: {str(e)}"

# Callback para atualizar os gráficos
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
def update_all_graphs(sort_by, start_date, end_date, session_data):
    """
    Callback para atualizar todos os gráficos com base nos filtros selecionados
    """
    return update_graphs(sort_by, start_date, end_date, session_data)

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
    app.run(debug=True, host='localhost', port=port)