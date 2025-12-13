import os, uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from .models import db, User, Unit, Case, MediaFile, Feedback, Notification, Role, CaseStatus

UPLOAD_FOLDER = "app/static/uploads"
ALLOWED_EXTENSIONS = {"png","jpg","jpeg","gif","mp4","mov"}

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY","devsecret")
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///app.db"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 初始化資料庫
    @app.cli.command("db-init")
    def db_init():
        with app.app_context():
            db.create_all()

            # 建立管理員帳號
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    account_id=f"A-{uuid.uuid4().hex[:8]}",
                    username="admin",
                    email="admin@example.com",
                    password_hash=generate_password_hash("admin123"),
                    role=Role.ADMIN,
                    is_active=True
                )
                db.session.add(admin)

            # 建立單位資料
            if not Unit.query.first():
                db.session.add(Unit(unit_name="初步接收單位"))
                db.session.add(Unit(unit_name="公共工程局"))
                db.session.add(Unit(unit_name="警方"))

            # 建立一個單位帳號
            if not User.query.filter_by(username="unit_demo").first():
                unit_user = User(
                    account_id=f"U-{uuid.uuid4().hex[:8]}",
                    username="unit_demo",
                    email="unit@example.com",
                    password_hash=generate_password_hash("unit123"),
                    role=Role.UNIT,
                    is_active=True
                )
                db.session.add(unit_user)

            db.session.commit()
            print("DB initialized (含 admin 與 unit_demo 帳號)")

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route("/register", methods=["GET","POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")
            if not username or not password:
                flash("請輸入必要欄位")
                return redirect(url_for("register"))
            if User.query.filter_by(username=username).first():
                flash("帳號已存在")
                return redirect(url_for("register"))
            user = User(
                account_id=f"U-{uuid.uuid4().hex[:8]}",
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role=Role.USER
            )
            db.session.add(user)
            db.session.commit()
            flash("註冊成功，請登入")
            return redirect(url_for("login"))
        return render_template("auth_register.html")

    @app.route("/login", methods=["GET","POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            user = User.query.filter_by(username=username, is_active=True).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for("index"))
            flash("帳號或密碼錯誤")
        return render_template("auth_login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/oauth/<provider>")
    def oauth_login(provider):
        flash(f"{provider} 登入尚未設定，請用一般登入")
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        q = request.args.get("q","")
        event_type = request.args.get("event_type","")
        cases = Case.query
        if q:
            cases = cases.filter(Case.description.contains(q) | Case.location_text.contains(q) | Case.case_id.contains(q))
        if event_type:
            cases = cases.filter_by(event_type=event_type)
        cases = cases.order_by(Case.report_time.desc()).limit(50).all()
        return render_template("index.html", cases=cases, q=q, event_type=event_type)

    @app.route("/case/new", methods=["GET","POST"])
    @login_required
    def case_new():
        if request.method == "POST":
            description = request.form.get("description")
            location_text = request.form.get("location_text")
            latitude = request.form.get("latitude")
            longitude = request.form.get("longitude")
            incident_time = request.form.get("incident_time")
            event_type = request.form.get("event_type")
            if not description or not event_type:
                flash("請輸入事件描述與類型")
                return redirect(url_for("case_new"))
            cid = f"A{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
            case = Case(
                case_id=cid,
                description=description,
                location_text=location_text,
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                incident_time=datetime.fromisoformat(incident_time) if incident_time else None,
                event_type=event_type,
                status=CaseStatus.SUBMITTED,
                user_id=current_user.id
            )
            db.session.add(case)
            db.session.commit()
            files = request.files.getlist("media_files")
            for f in files:
                if f and allowed_file(f.filename):
                    fname = secure_filename(f.filename)
                    save_name = f"{cid}_{uuid.uuid4().hex[:8]}_{fname}"
                    f.save(os.path.join(UPLOAD_FOLDER, save_name))
                    db.session.add(MediaFile(case_id=case.id, file_path=save_name, file_type=("video" if fname.lower().endswith(("mp4","mov")) else "image")))
            db.session.commit()
            db.session.add(Notification(user_id=current_user.id, message=f"案件 {cid} 已提交", type="app"))
            db.session.commit()
            flash("通報成功")
            return redirect(url_for("case_detail", case_id=case.case_id))
        return render_template("case_new.html")

    @app.route("/case/<case_id>")
    @login_required
    def case_detail(case_id):
        case = Case.query.filter_by(case_id=case_id).first_or_404()
        return render_template("case_detail.html", case=case)

    @app.route("/case/<case_id>/edit", methods=["GET","POST"])
    @login_required
    def case_edit(case_id):
        case = Case.query.filter_by(case_id=case_id, user_id=current_user.id).first_or_404()
        if case.status in [CaseStatus.ACCEPTED, CaseStatus.IN_PROGRESS, CaseStatus.COMPLETED]:
            flash("案件已被受理或處理中，無法更新/取消")
            return redirect(url_for("case_detail", case_id=case.case_id))
        if request.method == "POST":
            if request.form.get("action") == "cancel":
                case.status = CaseStatus.DRAFT
                db.session.add(Notification(user_id=current_user.id, message=f"案件 {case.case_id} 已取消", type="app"))
                db.session.commit()
                flash("已取消通報")
                return redirect(url_for("index"))
            case.description = request.form.get("description") or case.description
            case.location_text = request.form.get("location_text") or case.location_text
            case.latitude = float(request.form.get("latitude")) if request.form.get("latitude") else case.latitude
            case.longitude = float(request.form.get("longitude")) if request.form.get("longitude") else case.longitude
            db.session.commit()
            flash("更新成功")
            return redirect(url_for("case_detail", case_id=case.case_id))
        return render_template("case_edit.html", case=case)

    @app.route("/case/<case_id>/feedback", methods=["POST"])
    @login_required
    def case_feedback(case_id):
        case = Case.query.filter_by(case_id=case_id, user_id=current_user.id).first_or_404()
        rating = int(request.form.get("rating", 0))
        comments = request.form.get("comments","")
        if rating < 1 or rating > 5:
            flash("評分必須 1-5")
            return redirect(url_for("case_detail", case_id=case.case_id))
        fb = Feedback(case_id=case.id, rating=rating, comments=comments)
        db.session.add(fb)
        db.session.commit()
        flash("感謝您的回饋")
        return redirect(url_for("case_detail", case_id=case.case_id))

    def admin_required():
        return current_user.is_authenticated and current_user.role == Role.ADMIN

    @app.route("/admin", methods=["GET","POST"])
    @login_required
    def admin_dashboard():
        if not admin_required():
            flash("需要管理員權限")
            return redirect(url_for("index"))

        if request.method == "POST":
            action = request.form.get("action")
            if action == "create_unit":
                name = request.form.get("unit_name")
                if name:
                    db.session.add(Unit(unit_name=name))
                    db.session.commit()
                    flash("已新增處理單位")
            elif action == "suspend_user":
                uid = request.form.get("user_id")
                u = User.query.get(int(uid))
                if u:
                    u.is_active = False
                    db.session.commit()
                    flash("已停權使用者")
            elif action == "delete_user":
                uid = request.form.get("user_id")
                u = User.query.get(int(uid))
                if u:
                    u.is_active = False   # 標記停權
                    db.session.commit()
                    flash("已刪除使用者（案件保留）")

        # 🔑 加上這行，查詢所有使用者
        users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).all()
        cases = Case.query.order_by(Case.report_time.desc()).all()
        units = Unit.query.order_by(Unit.unit_name).all()

        return render_template("admin_dashboard.html", users=users, cases=cases, units=units)


    @app.route("/admin/case/<case_id>/review", methods=["POST"])
    @login_required
    def admin_case_review(case_id):
        if not admin_required():
            flash("需要管理員權限")
            return redirect(url_for("index"))
        case = Case.query.filter_by(case_id=case_id).first_or_404()
        act = request.form.get("action")
        if act == "mark_fake":
            case.is_fake = True
        elif act == "accept":
            case.status = CaseStatus.ACCEPTED
        elif act == "assign":
            unit_id = int(request.form.get("unit_id"))
            case.assigned_unit_id = unit_id
            case.status = CaseStatus.IN_PROGRESS
            db.session.commit()
            db.session.add(Notification(
                user_id=case.user_id,
                message=f"案件 {case.case_id} 已分派至單位 {unit_id}",
                type="app"
        ))
            db.session.commit()

        elif act == "complete":
            case.status = CaseStatus.COMPLETED
            db.session.commit()
            db.session.add(Notification(user_id=case.user_id, message=f"案件 {case.case_id} 狀態更新為 {case.status}", type="app"))
            db.session.commit()
        flash("已更新案件狀態")
        return redirect(url_for("admin_dashboard"))
    

    @app.route("/unit", methods=["GET","POST"])
    @login_required
    def unit_dashboard():
        if current_user.role not in [Role.ADMIN, Role.UNIT]:
            flash("需要單位權限")
            return redirect(url_for("index"))

        # 取得目前登入者的案件
        if current_user.role == Role.ADMIN:
            my_unit_cases = Case.query.all()
        else:
            my_unit_cases = Case.query.filter_by(assigned_unit_id=current_user.id).all()

        # 🔑 在這裡查詢所有單位，傳給模板
        units = Unit.query.order_by(Unit.unit_name).all()

        # 🔑 在 return 前把 units 一起傳給前端
        return render_template("unit_dashboard.html", cases=my_unit_cases, units=units)

    @app.route("/unit/case/<case_id>/reassign", methods=["POST"])
    @login_required
    def unit_reassign(case_id):
        if current_user.role != Role.UNIT:
            flash("需要單位權限")
            return redirect(url_for("index"))
        case = Case.query.filter_by(case_id=case_id).first_or_404()
        unit_id = int(request.form.get("unit_id"))
        case.assigned_unit_id = unit_id
        case.status = CaseStatus.IN_PROGRESS
        db.session.commit()
        db.session.add(Notification(
            user_id=case.user_id,
            message=f"案件 {case.case_id} 已轉派至單位 {unit_id}",
            type="app"
    ))
        db.session.commit()
        flash("案件已轉派")
        return redirect(url_for("unit_dashboard"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)

    return app

app = create_app()




