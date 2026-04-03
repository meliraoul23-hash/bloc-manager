Parfait ! 👍

---

## 📄 FICHIER 4 : `server.py` (le plus important !)

1. Cliquez **"Add file"** → **"Create new file"**
2. Nom : **`server.py`**
3. Contenu (copiez TOUT ce qui suit) :
Action: $ cat /app/bloc-manager-complet/server.py
Observation: from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, date
import base64
from bson import ObjectId
from io import BytesIO
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'bloc_usine_db')]

# Create the main app
app = FastAPI(title="Bloc Manager API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Helper function to serialize MongoDB documents
def serialize_doc(doc):
    if doc is None:
        return None
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc

# ============ MODELS ============
class EnterpriseCreate(BaseModel):
    name: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    logo_base64: Optional[str] = None

class UserCreate(BaseModel):
    phone: str
    pin: str
    name: str
    role: str  # patron, producteur, vendeur, comptable
    enterprise_id: str

class UserLogin(BaseModel):
    phone: str
    pin: str

class ProductCreate(BaseModel):
    code: str
    name: str
    category: str  # parpaing, hourdis, pave
    dimensions: Optional[str] = ""
    resistance: Optional[str] = ""
    price: int
    photo_base64: Optional[str] = None
    enterprise_id: str

class RawMaterialCreate(BaseModel):
    name: str
    unit: str
    quantity: float = 0
    min_stock_alert: float = 0
    enterprise_id: str

class RecipeCreate(BaseModel):
    name: str
    product_id: str
    materials: List[Dict[str, Any]]  # [{material_id, quantity}]
    yield_quantity: int
    enterprise_id: str

class ProductionCreate(BaseModel):
    recipe_id: str
    product_id: str
    quantity_produced: int
    rejects: int = 0
    production_date: str
    notes: Optional[str] = ""
    enterprise_id: str

class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = ""
    address: Optional[str] = ""
    enterprise_id: str

class OrderCreate(BaseModel):
    client_id: str
    items: List[Dict[str, Any]]  # [{product_id, quantity, unit_price}]
    tva_rate: float = 19.25
    enterprise_id: str

class PaymentCreate(BaseModel):
    order_id: str
    amount: int
    payment_method: str = "cash"  # cash, mobile_money, bank

# ============ ENTERPRISE ENDPOINTS ============
@api_router.post("/enterprises")
async def create_enterprise(enterprise: EnterpriseCreate):
    doc = enterprise.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.enterprises.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/enterprises/{enterprise_id}")
async def get_enterprise(enterprise_id: str):
    enterprise = await db.enterprises.find_one({"_id": ObjectId(enterprise_id)})
    if not enterprise:
        raise HTTPException(status_code=404, detail="Entreprise non trouvée")
    return serialize_doc(enterprise)

@api_router.put("/enterprises/{enterprise_id}")
async def update_enterprise(enterprise_id: str, enterprise: EnterpriseCreate):
    result = await db.enterprises.update_one(
        {"_id": ObjectId(enterprise_id)},
        {"$set": enterprise.model_dump()}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Entreprise non trouvée")
    return {"message": "Entreprise mise à jour"}

# ============ USER ENDPOINTS ============
@api_router.post("/users")
async def create_user(user: UserCreate):
    existing = await db.users.find_one({"phone": user.phone})
    if existing:
        raise HTTPException(status_code=400, detail="Ce numéro existe déjà")
    doc = user.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.users.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.post("/users/login")
async def login_user(credentials: UserLogin):
    user = await db.users.find_one({"phone": credentials.phone, "pin": credentials.pin})
    if not user:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    enterprise = await db.enterprises.find_one({"_id": ObjectId(user['enterprise_id'])})
    return {"user": serialize_doc(user), "enterprise": serialize_doc(enterprise)}

@api_router.get("/users/enterprise/{enterprise_id}")
async def get_users_by_enterprise(enterprise_id: str):
    users = await db.users.find({"enterprise_id": enterprise_id}).to_list(100)
    return [serialize_doc(u) for u in users]

# ============ PRODUCT ENDPOINTS ============
@api_router.post("/products")
async def create_product(product: ProductCreate):
    doc = product.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.products.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/products/enterprise/{enterprise_id}")
async def get_products(enterprise_id: str):
    products = await db.products.find({"enterprise_id": enterprise_id}).to_list(1000)
    return [serialize_doc(p) for p in products]

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, product: ProductCreate):
    result = await db.products.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": product.model_dump()}
    )
    return {"message": "Produit mis à jour"}

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    await db.products.delete_one({"_id": ObjectId(product_id)})
    return {"message": "Produit supprimé"}

# ============ RAW MATERIALS ENDPOINTS ============
@api_router.post("/materials")
async def create_material(material: RawMaterialCreate):
    doc = material.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.raw_materials.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/materials/enterprise/{enterprise_id}")
async def get_materials(enterprise_id: str):
    materials = await db.raw_materials.find({"enterprise_id": enterprise_id}).to_list(1000)
    return [serialize_doc(m) for m in materials]

@api_router.put("/materials/{material_id}")
async def update_material(material_id: str, material: RawMaterialCreate):
    result = await db.raw_materials.update_one(
        {"_id": ObjectId(material_id)},
        {"$set": material.model_dump()}
    )
    return {"message": "Matière mise à jour"}

# ============ RECIPE ENDPOINTS ============
@api_router.post("/recipes")
async def create_recipe(recipe: RecipeCreate):
    doc = recipe.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.recipes.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/recipes/enterprise/{enterprise_id}")
async def get_recipes(enterprise_id: str):
    recipes = await db.recipes.find({"enterprise_id": enterprise_id}).to_list(1000)
    return [serialize_doc(r) for r in recipes]

# ============ PRODUCTION ENDPOINTS ============
@api_router.post("/productions")
async def create_production(production: ProductionCreate):
    recipe = await db.recipes.find_one({"_id": ObjectId(production.recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recette non trouvée")
    
    for mat in recipe.get('materials', []):
        await db.raw_materials.update_one(
            {"_id": ObjectId(mat['material_id'])},
            {"$inc": {"quantity": -mat['quantity'] * (production.quantity_produced / recipe['yield_quantity'])}}
        )
    
    await db.finished_stocks.update_one(
        {"product_id": production.product_id, "enterprise_id": production.enterprise_id},
        {"$inc": {"quantity": production.quantity_produced}},
        upsert=True
    )
    
    product = await db.products.find_one({"_id": ObjectId(production.product_id)})
    doc = production.model_dump()
    doc['lot_number'] = f"LOT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    doc['product_name'] = product['name'] if product else "Inconnu"
    doc['recipe_name'] = recipe['name']
    doc['created_at'] = datetime.utcnow()
    result = await db.productions.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/productions/enterprise/{enterprise_id}")
async def get_productions(enterprise_id: str):
    productions = await db.productions.find({"enterprise_id": enterprise_id}).sort("created_at", -1).to_list(1000)
    return [serialize_doc(p) for p in productions]

# ============ STOCK ENDPOINTS ============
@api_router.get("/stocks/enterprise/{enterprise_id}")
async def get_stocks(enterprise_id: str):
    stocks = await db.finished_stocks.find({"enterprise_id": enterprise_id}).to_list(1000)
    for stock in stocks:
        product = await db.products.find_one({"_id": ObjectId(stock['product_id'])})
        stock['product_name'] = product['name'] if product else "Inconnu"
    return [serialize_doc(s) for s in stocks]

# ============ CLIENT ENDPOINTS ============
@api_router.post("/clients")
async def create_client(client: ClientCreate):
    doc = client.model_dump()
    doc['created_at'] = datetime.utcnow()
    result = await db.clients.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/clients/enterprise/{enterprise_id}")
async def get_clients(enterprise_id: str):
    clients = await db.clients.find({"enterprise_id": enterprise_id}).to_list(1000)
    return [serialize_doc(c) for c in clients]

# ============ ORDER ENDPOINTS ============
@api_router.post("/orders")
async def create_order(order: OrderCreate):
    client = await db.clients.find_one({"_id": ObjectId(order.client_id)})
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouvé")
    
    items_with_names = []
    subtotal = 0
    for item in order.items:
        product = await db.products.find_one({"_id": ObjectId(item['product_id'])})
        item_total = item['quantity'] * item['unit_price']
        items_with_names.append({
            **item,
            'product_name': product['name'] if product else "Inconnu",
            'total': item_total
        })
        subtotal += item_total
        await db.finished_stocks.update_one(
            {"product_id": item['product_id'], "enterprise_id": order.enterprise_id},
            {"$inc": {"quantity": -item['quantity']}}
        )
    
    tva_amount = int(subtotal * order.tva_rate / 100)
    total = subtotal + tva_amount
    
    count = await db.orders.count_documents({"enterprise_id": order.enterprise_id})
    order_number = f"CMD-{count + 1:05d}"
    
    doc = {
        "order_number": order_number,
        "client_id": order.client_id,
        "client_name": client['name'],
        "items": items_with_names,
        "subtotal": subtotal,
        "tva_rate": order.tva_rate,
        "tva_amount": tva_amount,
        "total": total,
        "paid_amount": 0,
        "remaining_amount": total,
        "status": "en_attente",
        "enterprise_id": order.enterprise_id,
        "created_at": datetime.utcnow()
    }
    result = await db.orders.insert_one(doc)
    doc['id'] = str(result.inserted_id)
    return doc

@api_router.get("/orders/enterprise/{enterprise_id}")
async def get_orders(enterprise_id: str):
    orders = await db.orders.find({"enterprise_id": enterprise_id}).sort("created_at", -1).to_list(1000)
    return [serialize_doc(o) for o in orders]

# ============ PAYMENT ENDPOINTS ============
@api_router.post("/payments")
async def create_payment(payment: PaymentCreate):
    order = await db.orders.find_one({"_id": ObjectId(payment.order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    
    new_paid = order['paid_amount'] + payment.amount
    new_remaining = order['total'] - new_paid
    new_status = "payee" if new_remaining <= 0 else "en_attente"
    
    await db.orders.update_one(
        {"_id": ObjectId(payment.order_id)},
        {"$set": {"paid_amount": new_paid, "remaining_amount": max(0, new_remaining), "status": new_status}}
    )
    
    payment_doc = {
        "order_id": payment.order_id,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "created_at": datetime.utcnow()
    }
    await db.payments.insert_one(payment_doc)
    return {"message": "Paiement enregistré", "new_remaining": max(0, new_remaining)}

# ============ DASHBOARD ============
@api_router.get("/dashboard/{enterprise_id}")
async def get_dashboard(enterprise_id: str):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    products_count = await db.products.count_documents({"enterprise_id": enterprise_id})
    clients_count = await db.clients.count_documents({"enterprise_id": enterprise_id})
    
    orders = await db.orders.find({"enterprise_id": enterprise_id}).to_list(1000)
    total_revenue = sum(o.get('total', 0) for o in orders)
    pending_payments = sum(o.get('remaining_amount', 0) for o in orders)
    
    materials = await db.raw_materials.find({"enterprise_id": enterprise_id}).to_list(1000)
    low_stock_materials = [m for m in materials if m.get('quantity', 0) <= m.get('min_stock_alert', 0)]
    
    return {
        "products_count": products_count,
        "clients_count": clients_count,
        "total_revenue": total_revenue,
        "pending_payments": pending_payments,
        "low_stock_count": len(low_stock_materials),
        "low_stock_materials": [serialize_doc(m) for m in low_stock_materials[:5]]
    }

# ============ SEED DATA ============
@api_router.post("/seed/{enterprise_id}")
async def seed_demo_data(enterprise_id: str):
    materials_data = [
        {"name": "Ciment", "unit": "sacs", "quantity": 100, "min_stock_alert": 20, "enterprise_id": enterprise_id},
        {"name": "Sable", "unit": "brouettes", "quantity": 200, "min_stock_alert": 50, "enterprise_id": enterprise_id},
        {"name": "Gravier", "unit": "brouettes", "quantity": 150, "min_stock_alert": 30, "enterprise_id": enterprise_id},
        {"name": "Eau", "unit": "litres", "quantity": 1000, "min_stock_alert": 200, "enterprise_id": enterprise_id},
    ]
    
    for mat in materials_data:
        existing = await db.raw_materials.find_one({"name": mat["name"], "enterprise_id": enterprise_id})
        if not existing:
            await db.raw_materials.insert_one(mat)
    
    products_data = [
        {"code": "P15", "name": "Parpaing 15", "category": "parpaing", "dimensions": "15x20x40", "resistance": "40 bars", "price": 350, "enterprise_id": enterprise_id},
        {"code": "P20", "name": "Parpaing 20", "category": "parpaing", "dimensions": "20x20x40", "resistance": "40 bars", "price": 450, "enterprise_id": enterprise_id},
        {"code": "H16", "name": "Hourdis 16", "category": "hourdis", "dimensions": "16x20x53", "resistance": "Standard", "price": 600, "enterprise_id": enterprise_id},
    ]
    
    for prod in products_data:
        existing = await db.products.find_one({"code": prod["code"], "enterprise_id": enterprise_id})
        if not existing:
            await db.products.insert_one(prod)
    
    clients_data = [
        {"name": "Client Demo 1", "phone": "+237699000001", "address": "Douala", "enterprise_id": enterprise_id},
        {"name": "Client Demo 2", "phone": "+237699000002", "address": "Yaoundé", "enterprise_id": enterprise_id},
    ]
    
    for client in clients_data:
        existing = await db.clients.find_one({"phone": client["phone"], "enterprise_id": enterprise_id})
        if not existing:
            await db.clients.insert_one(client)
    
    return {"message": "Données de démonstration ajoutées"}

# ============ HEALTH CHECK ============
@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Include the API router
app.include_router(api_router)

# Serve static files (frontend)
static_dir = ROOT_DIR / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    
    @app.get("/favicon.svg")
    async def favicon():
        return FileResponse(static_dir / "favicon.svg")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Serve index.html for all non-API routes (SPA)
        return FileResponse(static_dir / "index.html")

# Startup and shutdown events
@app.on_event("startup")
async def startup_db_client():
    logging.info("Connected to MongoDB")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
Exit code: 0
