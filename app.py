from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from models import db, Usuario, Produto, ProdutoLojista
from routes.admin import admin_bp
from routes.loja import loja_bp
from routes.pagamento import pagamento_bp
import os
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)

    # --- Banco de dados ---
    database_url = os.getenv('DATABASE_URL')
    ambiente = os.getenv('AMBIENTE', 'prod')

    if ambiente == 'prod' and not database_url:
        raise RuntimeError(
            "AMBIENTE=prod mas DATABASE_URL não definida. "
            "Não vou usar SQLite em produção por engano."
        )

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- Segurança JWT ---
    jwt_key = os.getenv('JWT_SECRET_KEY')
    if not jwt_key:
        raise RuntimeError(
            "JWT_SECRET_KEY não definida. Copie .env.example para .env e preencha."
        )
    app.config['JWT_SECRET_KEY'] = jwt_key

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    JWTManager(app)
    db.init_app(app)

    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(loja_bp, url_prefix='/api/loja')
    app.register_blueprint(pagamento_bp, url_prefix='/api/pagamento')

    @app.route('/api/health')
    def health():
        return {'status': 'ok'}

    with app.app_context():
        db.create_all()
        seed_dados()

    return app


def seed_dados():
    from auth import hash_senha

    admin_email = os.getenv('ADMIN_EMAIL')
    admin_senha = os.getenv('ADMIN_SENHA')
    ambiente = os.getenv('AMBIENTE', 'prod')

    # ---------- ADMIN INICIAL ----------
    if admin_email and admin_senha:
        ja_existe_admin = Usuario.query.filter_by(tipo='admin').first()
        if not ja_existe_admin:
            if len(admin_senha) < 8:
                print("❌ ADMIN_SENHA muito curta (mínimo 8 caracteres). Admin NÃO criado.")
            else:
                admin = Usuario(
                    nome='Admin Master',
                    email=admin_email.strip().lower(),
                    senha_hash=hash_senha(admin_senha),
                    tipo='admin',
                    precisa_trocar_senha=True
                )
                db.session.add(admin)
                db.session.commit()
                print("=" * 60)
                print(f"✅ Admin inicial criado: {admin.email}")
                print("⚠️  Será solicitada troca de senha no primeiro login.")
                print("=" * 60)
        else:
            print(f"ℹ️  Admin já existe ({ja_existe_admin.email}). Nada a fazer.")
    else:
        print("=" * 60)
        print("⚠️  ADMIN_EMAIL/ADMIN_SENHA não definidos no .env.")
        print("   Nenhum admin foi criado.")
        print("=" * 60)

    # ---------- DADOS DE EXEMPLO (apenas em dev) ----------
    if ambiente == 'dev':
        if not Usuario.query.filter_by(email='loja@teste.com').first():
            loja = Usuario(
                nome='Loja Exemplo',
                email='loja@teste.com',
                senha_hash=hash_senha('loja123'),
                tipo='loja',
                chave_pix='loja@teste.com'
            )
            db.session.add(loja)
            db.session.commit()

            admin = Usuario.query.filter_by(tipo='admin').first()
            produtos = [
                Produto(nome='Camiseta Básica', preco=59.90, comissao_percentual=10.0, estoque=100, admin_id=admin.id if admin else None),
                Produto(nome='Boné Premium', preco=89.90, comissao_percentual=12.0, estoque=50, admin_id=admin.id if admin else None),
                Produto(nome='Tênis Esportivo', preco=299.90, comissao_percentual=15.0, estoque=30, admin_id=admin.id if admin else None),
            ]
            db.session.add_all(produtos)
            db.session.commit()

            for p in produtos[:2]:
                db.session.add(ProdutoLojista(produto_id=p.id, loja_id=loja.id))
            db.session.commit()
            print("ℹ️  Dados de exemplo criados (loja@teste.com / loja123).")


app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('AMBIENTE') == 'dev'
    app.run(host='0.0.0.0', port=port, debug=debug)