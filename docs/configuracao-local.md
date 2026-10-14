# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha a seção `[firebase]`.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Instale as dependências com `pip install -r requirements.txt`.
4. Para executar todos os testes, use `python -m pytest tests`.
5. Inicie o app com `streamlit run app.py`. O cadastro permite preenchimento manual ou importação opcional de um documento Word (`.docx`).
