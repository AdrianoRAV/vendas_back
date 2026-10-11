from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity
from models import db, Usuario, Produto, ProdutoLojista, Solicitacao, Transacao
from auth import verificar_senha
from functools import wraps

loja_bp = Blueprint('loja', __name__)


def loja_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get('tipo') != 'loja':
            return jsonify({'erro': 'Acesso restrito à loja'}), 403
        return fn(*args, **kwargs)
    return wrapper


# ---------- LOGIN ----------
@loja_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user = Usuario.query.filter_by(email=data.get('email'), tipo='loja').first()
    if not user or not verificar_senha(data.get('senha', ''), user.senha_hash):
        return jsonify({'erro': 'Credenciais inválidas'}), 401
    token = create_access_token(identity=str(user.id), additional_claims={'tipo': 'loja'})
    return jsonify({'token': token, 'nome': user.nome, 'id': user.id})


# ---------- PERFIL (somente leitura + alterar chave pix permitida) ----------
@loja_bp.route('/perfil', methods=['GET'])
@loja_required
def perfil():
    loja_id = int(get_jwt_identity())
    l = Usuario.query.get(loja_id)
    return jsonify({
        'nome': l.nome, 'email': l.email,
        'chave_pix': l.chave_pix, 'saldo_a_receber': l.saldo_a_receber
    })


@loja_bp.route('/perfil/chave-pix', methods=['PUT'])
@loja_required
def atualizar_chave_pix():
    """Lojista pode atualizar apenas a própria chave Pix de recebimento."""
    loja_id = int(get_jwt_identity())
    l = Usuario.query.get(loja_id)
    data = request.get_json() or {}
    l.chave_pix = (data.get('chave_pix') or '').strip()
    db.session.commit()
    return jsonify({'msg': 'Chave Pix atualizada'})


# ---------- MEUS PRODUTOS (só os liberados) ----------
@loja_bp.route('/catalogo', methods=['GET'])
@loja_required
def catalogo():
    loja_id = int(get_jwt_identity())
    vinculos = ProdutoLojista.query.filter_by(loja_id=loja_id).all()
    ids = [v.produto_id for v in vinculos]
    produtos = Produto.query.filter(
        Produto.id.in_(ids), Produto.ativo == True
    ).all() if ids else []
    return jsonify([{
        'id': p.id, 'nome': p.nome, 'descricao': p.descricao,
        'preco': p.preco, 'estoque': p.estoque,
        'comissao_percentual': p.comissao_percentual
    } for p in produtos])


# ---------- SOLICITAÇÕES ----------
@loja_bp.route('/solicitacoes', methods=['GET'])
@loja_required
def listar_solicitacoes():
    loja_id = int(get_jwt_identity())
    sol = Solicitacao.query.filter_by(loja_id=loja_id).order_by(Solicitacao.criado_em.desc()).all()
    produtos = {p.id: p.nome for p in Produto.query.all()}
    return jsonify([{
        'id': s.id,
        'produto_id': s.produto_id,
        'produto_nome': produtos.get(s.produto_id, '—'),
        'quantidade': s.quantidade,
        'observacao': s.observacao,
        'status': s.status,
        'criado_em': s.criado_em.isoformat()
    } for s in sol])


@loja_bp.route('/solicitacoes', methods=['POST'])
@loja_required
def criar_solicitacao():
    loja_id = int(get_jwt_identity())
    data = request.get_json() or {}
    produto_id = data.get('produto_id')

    produto = Produto.query.get(produto_id)
    if not produto or not produto.ativo:
        return jsonify({'erro': 'Produto inválido'}), 404

    # Não permite solicitar algo que já está liberado
    if ProdutoLojista.query.filter_by(produto_id=produto_id, loja_id=loja_id).first():
        return jsonify({'erro': 'Produto já liberado para você'}), 400

    # Não permite duplicar solicitação pendente do mesmo produto
    existente = Solicitacao.query.filter_by(
        loja_id=loja_id, produto_id=produto_id, status='pendente'
    ).first()
    if existente:
        return jsonify({'erro': 'Você já solicitou este produto (pendente)'}), 400

    s = Solicitacao(
        loja_id=loja_id, produto_id=produto_id,
        quantidade=int(data.get('quantidade', 1)),
        observacao=data.get('observacao', '')
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({'id': s.id, 'msg': 'Solicitação enviada ao admin'}), 201


# ---------- PRODUTOS DISPONÍVEIS PARA SOLICITAR ----------
@loja_bp.route('/produtos-disponiveis', methods=['GET'])
@loja_required
def produtos_disponiveis():
    """Produtos ativos que o lojista ainda NÃO tem liberado."""
    loja_id = int(get_jwt_identity())
    vinculos = ProdutoLojista.query.filter_by(loja_id=loja_id).all()
    ids_liberados = [v.produto_id for v in vinculos]
    produtos = Produto.query.filter(
        Produto.ativo == True,
        ~Produto.id.in_(ids_liberados) if ids_liberados else True
    ).all()
    return jsonify([{
        'id': p.id, 'nome': p.nome, 'descricao': p.descricao,
        'preco': p.preco
    } for p in produtos])


# ---------- MINHAS TRANSAÇÕES (pagamentos gerados pelo admin para mim) ----------
@loja_bp.route('/minhas-transacoes', methods=['GET'])
@loja_required
def minhas_transacoes():
    loja_id = int(get_jwt_identity())
    trans = Transacao.query.filter_by(loja_id=loja_id).order_by(Transacao.criado_em.desc()).all()
    produtos = {p.id: p.nome for p in Produto.query.all()}
    return jsonify([{
        'id': t.id, 'uuid': t.uuid,
        'produto_nome': produtos.get(t.produto_id, '—'),
        'valor_pago': t.valor_pago,
        'repasse_loja': t.repasse_loja,
        'comissao': t.comissao,
        'status': t.status,
        'qr_code_base64': t.qr_code_base64,
        'criado_em': t.criado_em.isoformat()
    } for t in trans])