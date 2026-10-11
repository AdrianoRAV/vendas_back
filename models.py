from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # admin | loja
    chave_pix = db.Column(db.String(200), nullable=True)
    saldo_a_receber = db.Column(db.Float, default=0.0)
    precisa_trocar_senha = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Produto(db.Model):
    __tablename__ = 'produtos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, default='')
    preco = db.Column(db.Float, nullable=False)
    comissao_percentual = db.Column(db.Float, default=10.0)
    estoque = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ProdutoLojista(db.Model):
    """Quais produtos foram liberados para cada lojista."""
    __tablename__ = 'produtos_lojistas'
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    loja_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('produto_id', 'loja_id', name='uq_produto_loja'),)


class Solicitacao(db.Model):
    """Lojista solicita produto ao admin."""
    __tablename__ = 'solicitacoes'
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    quantidade = db.Column(db.Integer, default=1)
    observacao = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='pendente')  # pendente | aprovada | recusada
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Transacao(db.Model):
    __tablename__ = 'transacoes'
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(60), unique=True, nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'))
    loja_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    gerado_por_admin_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    valor_pago = db.Column(db.Float, nullable=False)
    comissao = db.Column(db.Float, nullable=False)
    repasse_loja = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='pendente')  # pendente | pago | expirado
    metodo = db.Column(db.String(30), default='pix')
    qr_code_base64 = db.Column(db.Text, default='')
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    pago_em = db.Column(db.DateTime, nullable=True)