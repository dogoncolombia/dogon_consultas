"""Local-only preview with fictional data. No real database or external writes."""
from ui_support import Database, make_app, report
from flask import request, session

db = Database()
db.tables["negative_reports"] += [report(8, name="Cliente Amarillo", document="222", phone="3002222222")]
app = make_app(db)
app.jinja_env.auto_reload = True


@app.before_request
def preview_session():
    if request.args.get("guest") == "1":
        session.clear()
    elif request.args.get("preview") == "1":
        session.update(user_id="test-user", rol="admin")


if __name__ == "__main__":
    print("Preview offline: datos ficticios, sin conexión a Supabase.")
    app.run(host="127.0.0.1", port=5055, debug=False)

