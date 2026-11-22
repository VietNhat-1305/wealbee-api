# Wealbee MCP chạy từ xa (Streamable HTTP tại /mcp). Build từ gốc repo:
#   docker build -f wb_mcp/Dockerfile -t wealbee-mcp .
#   docker run -p 8000:8000 -e WEALBEE_MCP_ALLOWED_HOSTS=mcp.wealbee.com wealbee-mcp
# Máy chủ không giữ khoá Wealbee: người dùng gửi khoá của mình qua header Authorization: Bearer <khoá>.
FROM python:3.12-slim
WORKDIR /app
COPY wb_mcp/requirements.txt wb_mcp/requirements.txt
RUN pip install --no-cache-dir -r wb_mcp/requirements.txt
COPY wb_mcp/ wb_mcp/
ENV PORT=8000
EXPOSE 8000
USER nobody
CMD ["python", "-m", "wb_mcp", "--http", "--host", "0.0.0.0"]
