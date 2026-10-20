import uvicorn

if __name__ == "__main__":
    print("Iniciando o servidor FastAPI do Sistema de Recondicionamento de Cabeçotes na porta 8080...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
