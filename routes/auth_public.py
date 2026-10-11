from flask import Blueprint, request, jsonify
from models import db, Usuario
from auth import hash_senha
import re

auth_public_bp = Blueprint('auth_public', __name__)

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validar_senha(senha: str):
    """Mínimo 8 caracteres, 1 letra e 1 número."""
    if len(senha) < 8:
        return 'Senha deve ter no mínimo 8 caracteres'
    if not re.search(r'[A-Za-z]', senha):
        return 'Senha deve conter ao menos uma letra'
    if not re.search(r'\d', senha):
        return 'Senha deve conter ao menos um número'
    return None


@auth_public_bp.route('/registro/loja', methods=['POST'])
def registro_loja():
    data = request.get_json() or {}

    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip().lower()
    senha = data.get('senha') or ''
    chave_pix = (data.get('chave_pix') or '').strip()

    # Validações
    if not nome or len(nome) < 3:
        return jsonify({'erro': 'Nome deve ter ao menos 3 caracteres'}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({'erro': 'E-mail inválido'}), 400
    erro_senha = validar_senha(senha)
    if erro_senha:
        return jsonify({'erro': erro_senha}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({'erro': 'E-mail já cadastrado'}), 409

    loja = Usuario(
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        tipo='loja',
        chave_pix=chave_pix,
        saldo_a_receber=0.0
    )
    db.session.add(loja)
    db.session.commit()

    return jsonify({
        'msg': 'Cadastro realizado com sucesso',
        'id': loja.id,
        'nome': loja.nome
    }), 201


@auth_public_bp.route('/registro/admin', methods=['POST'])
def registro_admin():
    """
    Só permite criar admin se NÃO existir nenhum admin ainda (bootstrap).
    Depois disso, novos admins só podem ser criados por admin logado.
    """
    total_admins = Usuario.query.filter_by(tipo='admin').count()
    if total_admins > 0:
        return jsonify({
            'erro': 'Já existe um admin. Use a rota autenticada para criar novos.'
        }), 403

    data = request.get_json() or {}
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip().lower()
    senha = data.get('senha') or ''

    if not nome or len(nome) < 3:
        return jsonify({'erro': 'Nome inválido'}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({'erro': 'E-mail inválido'}), 400
    erro_senha = validar_senha(senha)
    if erro_senha:
        return jsonify({'erro': erro_senha}), 400

    admin = Usuario(
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        tipo='admin'
    )
    db.session.add(admin)
    db.session.commit()

    return jsonify({'msg': 'Admin criado', 'id': admin.id}), 201


@auth_public_bp.route('/verificar-email', methods=['POST'])
def verificar_email():
    """Checa em tempo real se e-mail já está em uso (para UX do frontend)."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'disponivel': False}), 400
    existe = Usuario.query.filter_by(email=email).first() is not None
    return jsonify({'disponivel': not existe})