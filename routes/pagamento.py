import uuid
import base64
import io
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
import qrcode
from models import db, Produto, Transacao, Usuario

pagamento_bp = Blueprint('pagamento', __name__)


def gerar_qr_base64(payload: str) -> str:
    """Gera QR Code em base64 (simulação do Pix Copia e Cola)."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def gerar_payload_pix(valor: float, chave: str, txid: str) -> str:
    """
    Simula payload Pix EMV (formato real seria mais longo).
    Em produção: usar biblioteca `pix-python` ou gerar via API do PSP.
    """
    return f"00020126{len(chave):02d}{chave}5204000053039865406{valor:.2f}5802BR5913RECEBEDOR6009SAO PAULO62{len(txid):02d}{txid}6304ABCD"


@pagamento_bp.route('/criar', methods=['POST'])
@jwt_required()
def criar_pagamento():
    claims = get_jwt()
    if claims.get('tipo') != 'loja':
        return jsonify({'erro': 'Apenas lojas podem gerar pagamentos'}), 403

    loja_id = int(get_jwt_identity())
    data = request.get_json()
    produto_id = data.get('produto_id')
    valor_custom = data.get('valor')

    produto = Produto.query.get(produto_id)
    if not produto or not produto.ativo:
        return jsonify({'erro': 'Produto inválido'}), 404

    valor_pago = float(valor_custom) if valor_custom else produto.preco
    if valor_pago < produto.preco * 0.5:
        return jsonify({'erro': f'Valor mínimo: R$ {produto.preco * 0.5:.2f}'}), 400

    comissao = valor_pago * (produto.comissao_percentual / 100)
    repasse = valor_pago - comissao

    tx_uuid = str(uuid.uuid4())[:12]
    chave_recebedor = 'admin@sistema.com'
    payload = gerar_payload_pix(valor_pago, chave_recebedor, tx_uuid)
    qr_b64 = gerar_qr_base64(payload)

    tx = Transacao(
        uuid=tx_uuid, produto_id=produto_id, loja_id=loja_id,
        valor_pago=valor_pago, comissao=comissao, repasse_loja=repasse,
        status='pendente', metodo=data.get('metodo', 'pix'),
        qr_code_base64=qr_b64
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'transacao_uuid': tx_uuid,
        'valor_pago': valor_pago,
        'comissao': round(comissao, 2),
        'repasse_loja': round(repasse, 2),
        'payload_pix': payload,
        'qr_code_base64': qr_b64,
        'status': 'pendente'
    }), 201


@pagamento_bp.route('/simular-confirmacao/<tx_uuid>', methods=['POST'])
def simular_confirmacao(tx_uuid):
    """
    ATENÇÃO: rota apenas para teste.
    Em produção, esta confirmação viria via webhook do PSP com validação HMAC.
    """
    tx = Transacao.query.filter_by(uuid=tx_uuid).first()
    if not tx:
        return jsonify({'erro': 'Transação não encontrada'}), 404
    if tx.status == 'pago':
        return jsonify({'msg': 'Já pago'})

    tx.status = 'pago'
    tx.pago_em = datetime.utcnow()

    loja = Usuario.query.get(tx.loja_id)
    loja.saldo_a_receber = (loja.saldo_a_receber or 0) + tx.repasse_loja

    db.session.commit()
    return jsonify({'msg': 'Pagamento confirmado', 'status': 'pago'})


@pagamento_bp.route('/status/<tx_uuid>', methods=['GET'])
@jwt_required()
def status_pagamento(tx_uuid):
    tx = Transacao.query.filter_by(uuid=tx_uuid).first()
    if not tx:
        return jsonify({'erro': 'Não encontrada'}), 404
    return jsonify({
        'uuid': tx.uuid, 'status': tx.status,
        'valor_pago': tx.valor_pago,
        'repasse_loja': tx.repasse_loja,
        'comissao': tx.comissao
    })