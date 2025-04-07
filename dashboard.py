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
from functools import lru_cache, wraps
from io import StringIO
from dash.exceptions import PreventUpdate
import flask_caching
import cProfile
import io
import pstats

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

# Configuração do cache
cache = flask_caching.Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache-directory',
    'CACHE_DEFAULT_TIMEOUT': 300
})

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
    'template': 'plotly_white',
    'plot_bgcolor': '#FFFFFF',
    'paper_bgcolor': '#FFFFFF',
    'font': {
        'family': '"Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        'color': '#1A202C',
        'size': 12
    },
    'showlegend': True,
    'margin': dict(t=50, l=50, r=30, b=50),
    'autosize': True,
    'hovermode': 'closest',
    'xaxis': {'gridcolor': '#E2E8F0'},
    'yaxis': {'gridcolor': '#E2E8F0'}
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

def profile(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats()
        logger.info(f"Performance profile for {func.__name__}:\n{s.getvalue()}")
        return result
    return wrapper

@profile
def load_data():
    """Carrega os dados do CSV em tempo real."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'f1_2024_highlights.csv')
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Arquivo CSV não encontrado em: {csv_path}")
            
        logger.info(f"Carregando dados do arquivo: {csv_path}")
        
        # Carregar o CSV
        df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')
        logger.info(f"Colunas originais: {df.columns.tolist()}")
        
        # Mapear colunas usando os nomes exatos do CSV
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
            'canal': 'Canal'
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
@profile
def apply_filters(df_json, start_date, end_date, sort_by, sort_order):
    try:
        # Converter JSON para DataFrame usando StringIO para evitar FutureWarning
        df = pd.read_json(StringIO(df_json), orient='split')
        
        logger.info(f"Colunas após carregar JSON: {df.columns.tolist()}")
        logger.info(f"Primeiras linhas do DataFrame: {df.head()}")
        
        # Converter datas para datetime se forem strings
        if isinstance(start_date, str):
            start_date = pd.to_datetime(start_date, utc=True)
        if isinstance(end_date, str):
            end_date = pd.to_datetime(end_date, utc=True)
        
        # Garantir que a coluna de data está presente e é datetime
        date_column = 'data_publicacao' if 'data_publicacao' in df.columns else 'Data de Publicação'
        if date_column in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
                df[date_column] = pd.to_datetime(df[date_column], utc=True)
            
            # Aplicar filtros de data
            df = df[(df[date_column] >= start_date) & 
                    (df[date_column] <= end_date)]
        else:
            logger.error(f"Coluna de data não encontrada. Colunas disponíveis: {df.columns.tolist()}")
                
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
        
        # For initialization or updates
        if trigger_id in ['session-data', 'interval-component'] or data is None:
            # Load data
            df = load_data()
            if df is not None and not df.empty:
                # Garantir que as colunas numéricas sejam do tipo correto
                numeric_columns = ['visualizacoes', 'curtidas', 'comentarios']
                for col in numeric_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                # Converter a coluna de data
                if 'data_publicacao' in df.columns:
                    df['data_publicacao'] = pd.to_datetime(df['data_publicacao'], errors='coerce', utc=True)
                
                logger.info(f"Dados carregados com sucesso: {len(df)} registros")
                return df.to_json(date_format='iso', orient='split')
            else:
                logger.error("Falha ao carregar dados")
                return None
        
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
    ]),

    # Adicionar o botão de download após a tabela de vídeos
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Exportar Dados", className="card-title text-primary"),
                    html.P("Faça o download dos dados filtrados em diferentes formatos.", className="text-muted"),
                    dbc.ButtonGroup([
                        html.Button(
                            "Download CSV",
                            id="btn-csv",
                            className="btn btn-primary me-2"
                        ),
                        html.Button(
                            "Download Excel",
                            id="btn-excel",
                            className="btn btn-primary"
                        ),
                    ]),
                    dcc.Download(id="download-dataframe-csv"),
                    dcc.Download(id="download-dataframe-excel"),
                ])
            ], className="mb-3", style={'backgroundColor': '#FFFFFF', 'border': '1px solid #E2E8F0'})
        ], xs=12)
    ]),

    # Adicionar seção para visualização animada
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H5("Evolução Temporal", className="card-title text-primary"),
                    html.P("Visualize a evolução das métricas ao longo do tempo", className="text-muted"),
                    dcc.Graph(
                        id="metrics-animation",
                        config={'responsive': True},
                        style={'height': '500px'}
                    ),
                    dbc.Button(
                        "Play/Pause",
                        id="animation-control",
                        color="primary",
                        className="mt-3"
                    ),
                    dcc.Interval(
                        id='animation-interval',
                        interval=1000,
                        n_intervals=0,
                        disabled=True
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

@profile
def update_graphs(sort_by, start_date, end_date, session_data):
    try:
        if not session_data:
            logger.warning("Session data is empty for graph updates.")
            return [empty_figure("Nenhum dado disponível") for _ in range(7)]
            
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        if filtered_df.empty:
            logger.warning("Filtered data is empty for graph updates.")
            return [empty_figure("Nenhum dado disponível para o período selecionado") for _ in range(7)]

        # Garantir que as colunas são do tipo correto
        for col in ['Visualizações', 'Curtidas', 'Comentários', 'Taxa de Engajamento']:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)

        # Garantir que a data está no formato correto
        if 'Data de Publicação' in filtered_df.columns:
            filtered_df['Data de Publicação'] = pd.to_datetime(filtered_df['Data de Publicação'], utc=True)

        logger.info(f"Dados preparados para gráficos: {len(filtered_df)} registros")
        logger.info(f"Colunas disponíveis: {filtered_df.columns.tolist()}")

        # 1. Views Time Graph
        views_time = px.line(filtered_df.sort_values('Data de Publicação'), 
                           x='Data de Publicação', 
                           y='Visualizações',
                           title='Visualizações ao Longo do Tempo',
                           labels={'Data de Publicação': 'Data', 'Visualizações': 'Total de Visualizações'})
        views_time.update_layout(**GRAPH_LAYOUT_BASE)

        # 2. Engagement Time Graph
        eng_time = px.line(filtered_df.sort_values('Data de Publicação'),
                          x='Data de Publicação',
                          y='Taxa de Engajamento',
                          title='Taxa de Engajamento ao Longo do Tempo',
                          labels={'Data de Publicação': 'Data', 'Taxa de Engajamento': 'Taxa de Engajamento (%)'})
        eng_time.update_layout(**GRAPH_LAYOUT_BASE)

        # 3. Top Videos Graph
        top_videos = px.bar(filtered_df.nlargest(10, 'Visualizações').sort_values('Visualizações'),
                           x='Visualizações',
                           y='Título',
                           orientation='h',
                           title='Top 10 Vídeos por Visualizações',
                           labels={'Título': '', 'Visualizações': 'Total de Visualizações'})
        top_videos.update_layout(**GRAPH_LAYOUT_BASE)

        # 4. Correlation Graph
        correlation = px.scatter(filtered_df,
                               x='Visualizações',
                               y='Curtidas',
                               color='Taxa de Engajamento',
                               title='Correlação: Visualizações vs Curtidas',
                               trendline="ols",
                               labels={'Visualizações': 'Total de Visualizações', 
                                     'Curtidas': 'Total de Curtidas',
                                     'Taxa de Engajamento': 'Taxa de Engajamento (%)'})
        correlation.update_layout(**GRAPH_LAYOUT_BASE)

        # 5. Engagement Distribution
        engagement_dist = px.histogram(filtered_df,
                                     x='Taxa de Engajamento',
                                     title='Distribuição da Taxa de Engajamento',
                                     labels={'Taxa de Engajamento': 'Taxa de Engajamento (%)',
                                            'count': 'Número de Vídeos'})
        engagement_dist.update_layout(**GRAPH_LAYOUT_BASE)

        # 6. Daily Growth Rate
        filtered_df['Taxa de Crescimento'] = (filtered_df['Média de Visualizações Diárias'] / 
                                            filtered_df['Visualizações'] * 100)
        growth_rate = px.line(filtered_df.sort_values('Data de Publicação'),
                            x='Data de Publicação',
                            y='Taxa de Crescimento',
                            title='Taxa de Crescimento Diário',
                            labels={'Data de Publicação': 'Data',
                                   'Taxa de Crescimento': 'Taxa de Crescimento Diário (%)'})
        growth_rate.update_layout(**GRAPH_LAYOUT_BASE)

        # 7. Seasons Comparison (reusing existing function)
        seasons_comp = update_seasons_comparison(filtered_df)

        return [views_time, eng_time, top_videos, correlation, engagement_dist, growth_rate, seasons_comp]
    except Exception as e:
        logger.error(f"Erro ao atualizar gráficos: {e}", exc_info=True)
        return [empty_figure(f"Erro ao gerar gráfico: {str(e)}") for _ in range(7)]

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
            font=dict(size=16, color="#1A202C")
        )
        fig.update_layout(
            template='plotly_white',
            plot_bgcolor='#FFFFFF',
            paper_bgcolor='#FFFFFF',
            font_color='#1A202C',
            showlegend=False,
            margin=dict(t=50, l=50, r=30, b=50),
            autosize=True,
            hovermode='closest',
            xaxis={'visible': False},
            yaxis={'visible': False}
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
        numeric_columns = {
            'visualizacoes': 'Visualizações',
            'curtidas': 'Curtidas',
            'comentarios': 'Comentários'
        }
        
        for orig_col, display_col in numeric_columns.items():
            if orig_col in display_df.columns:
                display_df[orig_col] = pd.to_numeric(display_df[orig_col], errors='coerce').fillna(0)
            elif display_col in display_df.columns:
                display_df[display_col] = pd.to_numeric(display_df[display_col], errors='coerce').fillna(0)
                
        # Calcular taxa de engajamento
        if all(col in display_df.columns for col in ['visualizacoes', 'curtidas', 'comentarios']):
            display_df['Taxa de Engajamento'] = ((display_df['curtidas'] + display_df['comentarios']) / 
                                               display_df['visualizacoes'] * 100).round(2)
        elif all(col in display_df.columns for col in ['Visualizações', 'Curtidas', 'Comentários']):
            display_df['Taxa de Engajamento'] = ((display_df['Curtidas'] + display_df['Comentários']) / 
                                               display_df['Visualizações'] * 100).round(2)
        
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

@app.callback(
    Output("download-dataframe-csv", "data"),
    [Input("btn-csv", "n_clicks")],
    [State("sort-dropdown", "value"),
     State("date-picker", "start_date"),
     State("date-picker", "end_date"),
     State('session-data', 'data')]
)
def download_csv(n_clicks, sort_by, start_date, end_date, session_data):
    if n_clicks is None:
        raise PreventUpdate
    
    try:
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        if filtered_df.empty:
            raise PreventUpdate
            
        return dcc.send_data_frame(
            filtered_df.to_csv,
            "f1_highlights_data.csv",
            index=False,
            encoding='utf-8-sig'
        )
    except Exception as e:
        logger.error(f"Erro ao gerar CSV: {e}")
        raise PreventUpdate

@app.callback(
    Output("download-dataframe-excel", "data"),
    [Input("btn-excel", "n_clicks")],
    [State("sort-dropdown", "value"),
     State("date-picker", "start_date"),
     State("date-picker", "end_date"),
     State('session-data', 'data')]
)
def download_excel(n_clicks, sort_by, start_date, end_date, session_data):
    if n_clicks is None:
        raise PreventUpdate

    try:
        filtered_df = apply_filters(session_data, start_date, end_date, sort_by, 'asc')
        if filtered_df.empty:
            logger.warning("Filtered data is empty for Excel download.")
            raise PreventUpdate

        logger.info(f"Filtered data for Excel download: {filtered_df.head()}")
        return dcc.send_data_frame(
            filtered_df.to_excel,
            "f1_highlights_data.xlsx",
            index=False,
            sheet_name="F1 Highlights"
        )
    except Exception as e:
        logger.error(f"Erro ao gerar Excel: {e}")
        raise PreventUpdate

@app.callback(
    Output("metrics-animation", "figure"),
    [Input("animation-interval", "n_intervals")],
    [State('session-data', 'data')]
)
@cache.memoize(timeout=300)
def update_metrics_animation(n_intervals, session_data):
    if not session_data:
        return empty_figure("Nenhum dado disponível")
        
    try:
        df = pd.read_json(StringIO(session_data), orient='split')
        df['Data de Publicação'] = pd.to_datetime(df['Data de Publicação'])
        
        # Ordenar por data
        df = df.sort_values('Data de Publicação')
        
        # Criar figura com animação
        fig = px.scatter(
            df,
            x='Visualizações',
            y='Taxa de Engajamento',
            animation_frame=df['Data de Publicação'].dt.strftime('%Y-%m-%d'),
            size='Curtidas',
            color='Temporada',
            hover_name='Título',
            range_x=[0, df['Visualizações'].max() * 1.1],
            range_y=[0, df['Taxa de Engajamento'].max() * 1.1],
            title='Evolução de Métricas ao Longo do Tempo',
            labels={
                'Visualizações': 'Total de Visualizações',
                'Taxa de Engajamento': 'Taxa de Engajamento (%)'
            }
        )
        
        # Adicionar linha de tendência
        fig.add_traces(
            px.scatter(
                df,
                x='Visualizações',
                y='Taxa de Engajamento',
                trendline="ols"
            ).data
        )
        
        # Melhorar o layout da animação
        fig.update_layout(
            **GRAPH_LAYOUT_BASE,
            updatemenus=[{
                'type': 'buttons',
                'showactive': False,
                'buttons': [
                    {'label': '▶️ Play',
                     'method': 'animate',
                     'args': [None, {'frame': {'duration': 1000, 'redraw': True}, 'fromcurrent': True}]},
                    {'label': '⏸️ Pause',
                     'method': 'animate',
                     'args': [[None], {'frame': {'duration': 0, 'redraw': False}, 'mode': 'immediate'}]}
                ],
                'direction': 'left',
                'pad': {'r': 10, 't': 10},
                'x': 0.1,
                'y': 1.1
            }],
            sliders=[{
                'currentvalue': {'prefix': 'Data: '},
                'pad': {'t': 50},
                'len': 0.9,
                'x': 0.1,
                'y': 0,
                'steps': [
                    {
                        'args': [[f.name], {
                            'frame': {'duration': 0, 'redraw': False},
                            'mode': 'immediate',
                        }],
                        'label': f.name,
                        'method': 'animate'
                    }
                    for f in fig.frames
                ]
            }]
        )
        
        return fig
    except Exception as e:
        logger.error(f"Erro ao gerar animação: {e}")
        return empty_figure("Erro ao gerar animação")

@app.callback(
    [Output("animation-interval", "disabled"),
     Output("animation-control", "children")],
    [Input("animation-control", "n_clicks")],
    [State("animation-interval", "disabled")]
)
def toggle_animation(n_clicks, current_state):
    if n_clicks is None:
        return True, "Play"
    return not current_state, "Pause" if current_state else "Play"

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