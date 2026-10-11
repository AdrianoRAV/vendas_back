from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity
from models import db, Usuario, Produto, Transacao, ProdutoLojista, Solicitacao
from auth import verificar_senha, hash_senha
from functools import wraps
from sqlalchemy import func
import re

admin_bp = Blueprint('admin', __name__)


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get('tipo') != 'admin':
            return jsonify({'erro': 'Acesso restrito ao admin'}), 403
        return fn(*args, **kwargs)
    return wrapper


# ---------- LOGIN ----------
@admin_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user = Usuario.query.filter_by(email=data.get('email'), tipo='admin').first()
    if not user or not verificar_senha(data.get('senha', ''), user.senha_hash):
        return jsonify({'erro': 'Credenciais inválidas'}), 401
    token = create_access_token(identity=str(user.id), additional_claims={'tipo': 'admin'})
    return jsonify({
        'token': token,
        'nome': user.nome,
        'id': user.id,
        'precisa_trocar_senha': bool(user.precisa_trocar_senha)
    })


# ---------- DASHBOARD ----------
@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    total_vendas = db.session.query(func.sum(Transacao.valor_pago)).filter_by(status='pago').scalar() or 0
    total_comissao = db.session.query(func.sum(Transacao.comissao)).filter_by(status='pago').scalar() or 0
    total_repasse = db.session.query(func.sum(Transacao.repasse_loja)).filter_by(status='pago').scalar() or 0
    return jsonify({
        'total_vendas': round(total_vendas, 2),
        'total_comissao': round(total_comissao, 2),
        'total_repasse': round(total_repasse, 2),
        'total_produtos': Produto.query.count(),
        'total_lojas': Usuario.query.filter_by(tipo='loja').count(),
        'total_solicitacoes_pendentes': Solicitacao.query.filter_by(status='pendente').count()
    })


# ---------- PRODUTOS ----------
@admin_bp.route('/produtos', methods=['GET'])
@admin_required
def listar_produtos():
    produtos = Produto.query.all()
    return jsonify([{
        'id': p.id, 'nome': p.nome, 'descricao': p.descricao,
        'preco': p.preco, 'comissao_percentual': p.comissao_percentual,
        'estoque': p.estoque, 'ativo': p.ativo
    } for p in produtos])


@admin_bp.route('/produtos', methods=['POST'])
@admin_required
def criar_produto():
    data = request.get_json() or {}
    try:
        admin_id = int(get_jwt_identity())
        p = Produto(
            nome=data['nome'],
            descricao=data.get('descricao', ''),
            preco=float(data['preco']),
            comissao_percentual=float(data.get('comissao_percentual', 10.0)),
            estoque=int(data.get('estoque', 0)),
            admin_id=admin_id
        )
        db.session.add(p)
        db.session.commit()
        return jsonify({'id': p.id, 'msg': 'Produto criado'}), 201
    except Exception as e:
        return jsonify({'erro': str(e)}), 400


@admin_bp.route('/produtos/<int:pid>', methods=['DELETE'])
@admin_required
def deletar_produto(pid):
    p = Produto.query.get_or_404(pid)
    ProdutoLojista.query.filter_by(produto_id=pid).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify({'msg': 'Produto removido'})


# ---------- LOJISTAS ----------
@admin_bp.route('/lojas', methods=['GET'])
@admin_required
def listar_lojas():
    lojas = Usuario.query.filter_by(tipo='loja').all()
    return jsonify([{
        'id': l.id, 'nome': l.nome, 'email': l.email,
        'chave_pix': l.chave_pix, 'saldo_a_receber': l.saldo_a_receber
    } for l in lojas])


@admin_bp.route('/lojas', methods=['POST'])
@admin_required
def criar_loja():
    data = request.get_json() or {}
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip().lower()
    senha = data.get('senha') or ''

    if len(nome) < 3:
        return jsonify({'erro': 'Nome muito curto'}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'erro': 'E-mail inválido'}), 400
    if len(senha) < 6:
        return jsonify({'erro': 'Senha deve ter no mínimo 6 caracteres'}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({'erro': 'E-mail já cadastrado'}), 409

    loja = Usuario(
        nome=nome, email=email,
        senha_hash=hash_senha(senha),
        tipo='loja',
        chave_pix=(data.get('chave_pix') or '').strip()
    )
    db.session.add(loja)
    db.session.commit()
    return jsonify({'id': loja.id, 'msg': 'Lojista cadastrado'}), 201


@admin_bp.route('/lojas/<int:loja_id>', methods=['PUT'])
@admin_required
def atualizar_loja(loja_id):
    loja = Usuario.query.filter_by(id=loja_id, tipo='loja').first_or_404()
    data = request.get_json() or {}
    if 'nome' in data: loja.nome = data['nome']
    if 'chave_pix' in data: loja.chave_pix = data['chave_pix']
    if 'senha' in data and data['senha']:
        loja.senha_hash = hash_senha(data['senha'])
    db.session.commit()
    return jsonify({'msg': 'Lojista atualizado'})


@admin_bp.route('/lojas/<int:loja_id>', methods=['DELETE'])
@admin_required
def deletar_loja(loja_id):
    loja = Usuario.query.filter_by(id=loja_id, tipo='loja').first_or_404()
    ProdutoLojista.query.filter_by(loja_id=loja_id).delete()
    Solicitacao.query.filter_by(loja_id=loja_id).delete()
    db.session.delete(loja)
    db.session.commit()
    return jsonify({'msg': 'Lojista removido'})


# ---------- LIBERAR PRODUTOS PARA LOJISTA ----------
@admin_bp.route('/lojas/<int:loja_id>/produtos', methods=['GET'])
@admin_required
def produtos_da_loja(loja_id):
    vinculos = ProdutoLojista.query.filter_by(loja_id=loja_id).all()
    ids = [v.produto_id for v in vinculos]
    produtos = Produto.query.filter(Produto.id.in_(ids)).all() if ids else []
    return jsonify([{
        'id': p.id, 'nome': p.nome, 'preco': p.preco,
        'comissao_percentual': p.comissao_percentual
    } for p in produtos])


@admin_bp.route('/lojas/<int:loja_id>/produtos', methods=['POST'])
@admin_required
def liberar_produto(loja_id):
    data = request.get_json() or {}
    produto_id = data.get('produto_id')
    if not Produto.query.get(produto_id):
        return jsonify({'erro': 'Produto inválido'}), 404
    if not Usuario.query.filter_by(id=loja_id, tipo='loja').first():
        return jsonify({'erro': 'Loja inválida'}), 404
    if ProdutoLojista.query.filter_by(produto_id=produto_id, loja_id=loja_id).first():
        return jsonify({'msg': 'Já liberado'})
    db.session.add(ProdutoLojista(produto_id=produto_id, loja_id=loja_id))
    db.session.commit()
    return jsonify({'msg': 'Produto liberado'}), 201


@admin_bp.route('/lojas/<int:loja_id>/produtos/<int:produto_id>', methods=['DELETE'])
@admin_required
def revogar_produto(loja_id, produto_id):
    v = ProdutoLojista.query.filter_by(loja_id=loja_id, produto_id=produto_id).first()
    if not v:
        return jsonify({'erro': 'Vínculo não encontrado'}), 404
    db.session.delete(v)
    db.session.commit()
    return jsonify({'msg': 'Produto revogado'})


# ---------- SOLICITAÇÕES ----------
@admin_bp.route('/solicitacoes', methods=['GET'])
@admin_required
def listar_solicitacoes():
    sol = Solicitacao.query.order_by(Solicitacao.criado_em.desc()).all()
    # enriquece com nomes
    lojas = {u.id: u.nome for u in Usuario.query.filter_by(tipo='loja').all()}
    produtos = {p.id: p.nome for p in Produto.query.all()}
    return jsonify([{
        'id': s.id,
        'loja_id': s.loja_id,
        'loja_nome': lojas.get(s.loja_id, '—'),
        'produto_id': s.produto_id,
        'produto_nome': produtos.get(s.produto_id, '—'),
        'quantidade': s.quantidade,
        'observacao': s.observacao,
        'status': s.status,
        'criado_em': s.criado_em.isoformat()
    } for s in sol])


@admin_bp.route('/solicitacoes/<int:sid>', methods=['PUT'])
@admin_required
def responder_solicitacao(sid):
    s = Solicitacao.query.get_or_404(sid)
    data = request.get_json() or {}
    novo_status = data.get('status')
    if novo_status not in ('aprovada', 'recusada'):
        return jsonify({'erro': 'Status inválido'}), 400
    if s.status != 'pendente':
        return jsonify({'erro': 'Solicitação já respondida'}), 400

    s.status = novo_status
    if novo_status == 'aprovada':
        existe = ProdutoLojista.query.filter_by(
            produto_id=s.produto_id, loja_id=s.loja_id
        ).first()
        if not existe:
            db.session.add(ProdutoLojista(produto_id=s.produto_id, loja_id=s.loja_id))
    db.session.commit()
    return jsonify({'msg': f'Solicitação {novo_status}'})


# ---------- GERAR PAGAMENTO PARA LOJISTA ----------
@admin_bp.route('/lojas/<int:loja_id>/gerar-pagamento', methods=['POST'])
@admin_required
def admin_gerar_pagamento(loja_id):
    from routes.pagamento import gerar_payload_pix, gerar_qr_base64
    import uuid as _uuid

    loja = Usuario.query.filter_by(id=loja_id, tipo='loja').first()
    if not loja:
        return jsonify({'erro': 'Loja inválida'}), 404

    data = request.get_json() or {}
    produto_id = data.get('produto_id')
    valor = data.get('valor')

    produto = Produto.query.get(produto_id)
    if not produto:
        return jsonify({'erro': 'Produto inválido'}), 404

    if not ProdutoLojista.query.filter_by(produto_id=produto_id, loja_id=loja_id).first():
        return jsonify({'erro': 'Produto não liberado para esta loja'}), 403

    valor_pago = float(valor) if valor else produto.preco
    if valor_pago <= 0:
        return jsonify({'erro': 'Valor inválido'}), 400

    comissao = valor_pago * (produto.comissao_percentual / 100)
    repasse = valor_pago - comissao

    tx_uuid = str(_uuid.uuid4())[:12]
    chave_recebedor = 'admin@sistema.com'
    payload = gerar_payload_pix(valor_pago, chave_recebedor, tx_uuid)
    qr_b64 = gerar_qr_base64(payload)

    tx = Transacao(
        uuid=tx_uuid, produto_id=produto_id, loja_id=loja_id,
        gerado_por_admin_id=int(get_jwt_identity()),
        valor_pago=valor_pago, comissao=comissao, repasse_loja=repasse,
        status='pendente', metodo=data.get('metodo', 'pix'),
        qr_code_base64=qr_b64
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'transacao_uuid': tx_uuid,
        'loja_nome': loja.nome,
        'produto_nome': produto.nome,
        'valor_pago': valor_pago,
        'comissao': round(comissao, 2),
        'repasse_loja': round(repasse, 2),
        'payload_pix': payload,
        'qr_code_base64': qr_b64,
        'status': 'pendente'
    }), 201


# ---------- TRANSAÇÕES ----------
@admin_bp.route('/transacoes', methods=['GET'])
@admin_required
def listar_transacoes():
    trans = Transacao.query.order_by(Transacao.criado_em.desc()).all()
    lojas = {u.id: u.nome for u in Usuario.query.filter_by(tipo='loja').all()}
    produtos = {p.id: p.nome for p in Produto.query.all()}
    return jsonify([{
        'id': t.id, 'uuid': t.uuid,
        'produto_nome': produtos.get(t.produto_id, '—'),
        'loja_nome': lojas.get(t.loja_id, '—'),
        'valor_pago': t.valor_pago,
        'comissao': t.comissao,
        'repasse_loja': t.repasse_loja,
        'status': t.status,
        'metodo': t.metodo,
        'criado_em': t.criado_em.isoformat()
    } for t in trans])


@admin_bp.route('/transacoes/<tx_uuid>/confirmar', methods=['POST'])
@admin_required
def confirmar_transacao(tx_uuid):
    """Admin confirma manualmente que o Pix foi recebido (para testar sem PSP real)."""
    from datetime import datetime
    tx = Transacao.query.filter_by(uuid=tx_uuid).first()
    if not tx:
        return jsonify({'erro': 'Transação não encontrada'}), 404
    if tx.status == 'pago':
        return jsonify({'msg': 'Já estava paga'})
    tx.status = 'pago'
    tx.pago_em = datetime.utcnow()
    loja = Usuario.query.get(tx.loja_id)
    loja.saldo_a_receber = (loja.saldo_a_receber or 0) + tx.repasse_loja
    db.session.commit()
    return jsonify({'msg': 'Pagamento confirmado', 'status': 'pago'})


# ---------- CRIAR OUTRO ADMIN ----------
@admin_bp.route('/criar-admin', methods=['POST'])
@admin_required
def criar_admin():
    data = request.get_json() or {}
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip().lower()
    senha = data.get('senha') or ''

    if len(nome) < 3:
        return jsonify({'erro': 'Nome inválido'}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'erro': 'E-mail inválido'}), 400
    if len(senha) < 8:
        return jsonify({'erro': 'Senha fraca (mínimo 8 caracteres)'}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({'erro': 'E-mail já cadastrado'}), 409

    admin = Usuario(nome=nome, email=email, senha_hash=hash_senha(senha), tipo='admin')
    db.session.add(admin)
    db.session.commit()
    return jsonify({'msg': 'Admin criado', 'id': admin.id}), 201

# ---------- PERFIL DO ADMIN ----------
@admin_bp.route('/me', methods=['GET'])
@admin_required
def me():
    admin = Usuario.query.get(int(get_jwt_identity()))
    return jsonify({
        'id': admin.id,
        'nome': admin.nome,
        'email': admin.email,
        'precisa_trocar_senha': bool(admin.precisa_trocar_senha)
    })


@admin_bp.route('/trocar-senha', methods=['POST'])
@admin_required
def trocar_senha():
    data = request.get_json() or {}
    senha_atual = data.get('senha_atual', '')
    novo_email = (data.get('novo_email') or '').strip().lower()
    nova_senha = data.get('nova_senha', '')
    confirmar = data.get('confirmar', '')

    admin = Usuario.query.get(int(get_jwt_identity()))

    if not verificar_senha(senha_atual, admin.senha_hash):
        return jsonify({'erro': 'Senha atual incorreta'}), 401

    # Se veio um e-mail novo, valida e atualiza
    if novo_email and novo_email != admin.email:
        import re
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', novo_email):
            return jsonify({'erro': 'E-mail inválido'}), 400
        if Usuario.query.filter_by(email=novo_email).first():
            return jsonify({'erro': 'E-mail já em uso'}), 409
        admin.email = novo_email

    if nova_senha != confirmar:
        return jsonify({'erro': 'As senhas não coincidem'}), 400
    if len(nova_senha) < 8:
        return jsonify({'erro': 'Nova senha deve ter no mínimo 8 caracteres'}), 400
    if not any(c.isdigit() for c in nova_senha):
        return jsonify({'erro': 'Nova senha deve conter ao menos um número'}), 400
    if not any(c.isalpha() for c in nova_senha):
        return jsonify({'erro': 'Nova senha deve conter ao menos uma letra'}), 400
    if nova_senha == senha_atual:
        return jsonify({'erro': 'A nova senha deve ser diferente da atual'}), 400

    admin.senha_hash = hash_senha(nova_senha)
    admin.precisa_trocar_senha = False
    db.session.commit()

    return jsonify({
        'msg': 'Dados atualizados com sucesso',
        'email': admin.email
    })