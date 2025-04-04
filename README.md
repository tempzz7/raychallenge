# F1 YouTube Analytics

Este projeto analisa os vídeos de highlights das corridas de Fórmula 1 do canal oficial no YouTube, construindo um dashboard interativo para visualização dos dados.

## Demo

Acesse o dashboard em produção: [F1 YouTube Analytics Dashboard](https://raychallenge.onrender.com/)

## Funcionalidades

- **Coleta automática de dados**: Consome a API do YouTube para obter vídeos do canal oficial da F1
- **Filtragem inteligente**: Identifica e filtra vídeos de highlights das corridas
- **Dashboard interativo**: Visualize os dados com filtros por data e métricas
- **Análise de tendências**: Veja como o engajamento e visualizações evoluem ao longo do tempo
- **Visão completa**: Acesse detalhes como total de visualizações, curtidas e comentários

## Requisitos

- Python 3.8 ou superior
- Conta Google Cloud com YouTube Data API v3 habilitada
- Chave de API do YouTube

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/f1-youtube-analytics.git
cd f1-youtube-analytics
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure o arquivo `.env` com suas credenciais:
```
YOUTUBE_API_KEY=sua_chave_api_aqui
PLAYLIST_ID=id_da_playlist_aqui
```

## Uso

1. Execute a coleta de dados:
```bash
python app.py
```

2. Inicie o dashboard:
```bash
python dashboard.py
```

3. Acesse o dashboard em seu navegador:
```
http://127.0.0.1:8050/
```

## Decisões Técnicas

### API do YouTube
- Utilizei a biblioteca `googleapiclient` para consumir a API do YouTube, seguindo as melhores práticas de autenticação e requisições.
- Implementei paginação para garantir a coleta de todos os vídeos disponíveis na playlist.
- Adicionei filtros para identificar vídeos de highlights com base no título e descrição.

### Dashboard
- Escolhi o Dash (Plotly) por sua facilidade de uso e capacidade de criar visualizações interativas com poucas linhas de código.
- Utilizei o tema escuro para melhorar a legibilidade e reduzir o cansaço visual durante análises prolongadas.
- Implementei filtros de data e ordenação para permitir diferentes perspectivas dos dados.

### Organização do Código
- Adotei uma estrutura orientada a objetos para facilitar a manutenção e expansão.
- Separei a coleta de dados (app.py) da visualização (dashboard.py) para modularizar as funcionalidades.
- Implementei logging abrangente para facilitar o diagnóstico de problemas.
- CSS e HTML estruturados em assets.

### Processamento de Dados
- Utilizei o Pandas para manipulação eficiente dos dados coletados.
- Adicionei métricas derivadas como taxa de engajamento para enriquecer a análise.
- Salvei os dados em CSV para permitir análises offline e reduzir chamadas à API.

## Desafios Encontrados

### Limitações da API
- A API do YouTube tem cotas diárias que limitam o número de requisições, o que exigiu otimização das chamadas.
- Alguns vídeos tinham dados incompletos, necessitando tratamento robusto de erros.

### Processamento de Dados
- A identificação precisa dos vídeos de highlights exigiu combinação de filtros e análise de padrões nos títulos.
- A formatação de datas e durações dos vídeos demandou conversões específicas para garantir consistência.

### Visualização
- Criar um layout responsivo que funcionasse bem em diferentes dispositivos foi desafiador.
- Equilibrar a quantidade de informações no dashboard sem sobrecarregar a interface requereu várias iterações.

### Segurança
- O gerenciamento seguro das credenciais da API exigiu implementação cuidadosa com variáveis de ambiente.

### Frameworks
- Tive um problema com o Streamlib, tendo que migrar para o DASH, simplesmente por mais simples que fosse o código a interface ficava preta.


