from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import sqlite3
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "adminialulanches0" 
CORS(app)

DATABASE = 'lanchonete.db'

# --- Funções auxiliares ---
def criar_conexao(banco):
    conn = sqlite3.connect(banco)
    conn.row_factory = sqlite3.Row
    return conn

def criar_tabelas():
    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()

    # Tabelas de clientes, produtos, pedidos, itens_pedido
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            endereco TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            total REAL,
            forma_pagamento TEXT,
            tipo_entrega TEXT,
            status TEXT DEFAULT 'recebido',
            data_pedido TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            produto_id INTEGER,
            quantidade INTEGER,
            preco_unitario REAL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
            FOREIGN KEY (produto_id) REFERENCES produtos(id)
        )
    """)

    # 🔒 Tabela de usuários/admins
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL
        )
    """)

    # Inserir produtos de exemplo
    cursor.execute("SELECT COUNT(*) FROM produtos")
    if cursor.fetchone()[0] == 0:
        produtos_exemplo = [
            ("X-Salada", 16.00), ("X-Dog", 15.00), ("X-Bacon", 18.00),
            ("Pastel Carne", 14.00), ("Pastel Queijo", 14.00),
            ("Coca-Cola 2L", 12.00), ("Porção Batata Frita", 35.00)
        ]
        cursor.executemany("INSERT INTO produtos (nome, preco) VALUES (?, ?)", produtos_exemplo)

    # Criar usuário admin inicial
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        senha_hash = generate_password_hash("ialuadmin")  
        cursor.execute("INSERT INTO usuarios (username, senha_hash) VALUES (?, ?)", ("admin", senha_hash))

    conn.commit()
    conn.close()

# --- Decorador de proteção ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return jsonify({"error": "Não autorizado"}), 403
        return f(*args, **kwargs)
    return decorated

# --- Rotas de autenticação ---
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    # Aceita JSON ou form
    data = request.get_json() or request.form
    username = data.get("username")
    senha = data.get("senha")

    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT senha_hash FROM usuarios WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user["senha_hash"], senha):
        session["usuario"] = username
        return jsonify({"success": True, "message": "Login realizado com sucesso!"})
    return jsonify({"success": False, "message": "Usuário ou senha inválidos"}), 401

@app.route('/logout')
@login_required
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login_page"))

# --- Rotas principais ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/acompanhamento')
def acompanhamento():
    return render_template('acompanhamento.html')

@app.route('/painel')
@login_required
def painel():
    return render_template('painel.html')

# --- API de pedidos ---
@app.route('/api/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    if request.content_type != 'application/json':
        return jsonify({'error': 'Content-Type deve ser application/json'}), 415
    data = request.get_json()
    cliente_info = data.get('cliente', {})
    itens = data.get('itens', [])
    forma_pagamento = data.get('forma_pagamento', 'não especificado')
    tipo_pedido = data.get('tipo', 'retirada')

    if not cliente_info or not itens:
        return jsonify({'error': 'Dados incompletos'}), 400

    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()
    try:
        # Inserir cliente
        cursor.execute("INSERT INTO clientes (nome, telefone, endereco) VALUES (?, ?, ?)", (
            cliente_info.get('nome'),
            cliente_info.get('telefone'),
            cliente_info.get('endereco', '')
        ))
        cliente_id = cursor.lastrowid

        total = sum(item['price'] * item['quantity'] for item in itens)
        fuso = pytz.timezone('America/Sao_Paulo')
        data_pedido = datetime.now(fuso).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT INTO pedidos (cliente_id, total, forma_pagamento, tipo_entrega, status, data_pedido)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cliente_id, total, forma_pagamento, tipo_pedido, 'recebido', data_pedido))
        pedido_id = cursor.lastrowid

        for item in itens:
            cursor.execute("""
                INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?)
            """, (pedido_id, item['id'], item['quantity'], item['price']))

        conn.commit()
        return jsonify({'ok': True, 'message': 'Pedido finalizado', 'pedido_id': pedido_id}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/pedidos', methods=['GET'])
@login_required
def listar_pedidos():
    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.*, c.nome as cliente_nome, c.telefone as cliente_telefone, c.endereco as cliente_endereco
            FROM pedidos p
            JOIN clientes c ON p.cliente_id = c.id
            ORDER BY p.data_pedido DESC
        """)
        pedidos = cursor.fetchall()
        return jsonify([dict(pedido) for pedido in pedidos]), 200
    finally:
        conn.close()

@app.route('/api/pedidos/<int:pedido_id>/status', methods=['PUT'])
@login_required
def atualizar_status(pedido_id):
    data = request.get_json()
    novo_status = data.get('status')
    if not novo_status:
        return jsonify({'error': 'Status não fornecido'}), 400

    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo_status, pedido_id))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        return jsonify({'ok': True, 'message': 'Status atualizado'}), 200
    finally:
        conn.close()
        
@app.route('/api/pedidos/<int:pedido_id>', methods=['GET'])
def obter_pedido(pedido_id):
    conn = criar_conexao(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.id, p.total, p.forma_pagamento, p.tipo_entrega, p.status, p.data_pedido,
            c.nome as cliente_nome, c.telefone as cliente_telefone, c.endereco as cliente_endereco
            FROM pedidos p
            JOIN clientes c ON p.cliente_id = c.id
            WHERE p.id = ?
        """, (pedido_id,))
        pedido = cursor.fetchone()
        if not pedido:
            return jsonify({"error": "Pedido não encontrado"}), 404

        # Buscar itens do pedido
        cursor.execute("""
            SELECT i.quantidade, i.preco_unitario,
            pr.nome
            FROM itens_pedido i
            JOIN produtos pr ON i.produto_id = pr.id
            WHERE i.pedido_id = ?
        """, (pedido_id,))
        itens = cursor.fetchall()

        pedido_dict = dict(pedido)
        pedido_dict["itens"] = [dict(item) for item in itens]

        return jsonify(pedido_dict), 200
    finally:
        conn.close()


# --- Inicialização ---
if __name__ == '__main__':
    criar_tabelas()
    app.run(debug=True, port=5000)