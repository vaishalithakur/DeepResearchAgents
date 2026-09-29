from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str = None
    price: float

app = FastAPI()

@app.post("/items/")
def create_item(item: Item):
    return {"message": "Item created", "name": item.name, "description": item.description, "price": item.price}
