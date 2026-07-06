from backend.app import create_app
from backend.config import Config
from backend.services import ml
import json

app = create_app(Config)
with app.app_context():
    res = ml.entrenar()
    print(json.dumps(res, ensure_ascii=False))
