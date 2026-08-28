"""WSGI entry point: ``gunicorn wsgi:app`` in production, ``python wsgi.py`` locally."""

from splitmate import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
