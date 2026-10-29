from typing import List, Optional, Type
import os
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column, Integer, String, ForeignKey,
    create_engine, event
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    Session, declarative_base, sessionmaker, relationship
)

# =====================================================
# 1. BASE DE DATOS SQLITE
# =====================================================

engine = create_engine(os.getenv("DATABASE_URL"))

SessionLocal = sessionmaker(
    bind=engine,
)

SessionLocal = sessionmaker(
    bind=engine,
)
# Clase base de la que heredan todas las tablas
Base = declarative_base()

# Abre una sesión por petición y la cierra al terminar
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# 2. TABLA MATERIAS
# =====================================================
# Tabla materias: guarda el nombre de cada materia (único y obligatorio)
class Materia(Base):
    __tablename__ = "materias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)


# =====================================================
# 3. TABLA PARALELOS
# =====================================================

class Paralelo(Base):
    __tablename__ = "paralelos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(20), nullable=False, unique=True)

    materia_guia_id = Column(
        Integer,
        ForeignKey("materias.id"),
        unique=True,
        nullable=True
    )

    materia_guia = relationship(
        "Materia",
        backref="paralelo_guia",
        uselist=False
    )

    usuarios = relationship(
        "Usuario",
        back_populates="paralelo"
    )


# =====================================================
# 4. TABLA USUARIOS
# =====================================================

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    apellido = Column(String(50), nullable=False)
    edad = Column(Integer, nullable=False)
    genero = Column(String(10), nullable=False)

    paralelo_id = Column(
        Integer,
        ForeignKey("paralelos.id"),
        nullable=True
    )

    paralelo = relationship(
        "Paralelo",
        back_populates="usuarios"
    )


# =====================================================
# 5. ESQUEMAS DE DATOS
# =====================================================

class MateriaIn(BaseModel):
    nombre: str


class MateriaOut(MateriaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ParaleloIn(BaseModel):
    nombre: str
    materia_guia_id: Optional[int] = None


class ParaleloOut(ParaleloIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class UsuarioIn(BaseModel):
    nombre: str
    apellido: str
    edad: int
    genero: str
    paralelo_id: Optional[int] = None


class UsuarioOut(UsuarioIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


# =====================================================
# 6. FUNCION CRUD
# =====================================================

 # Genera las rutas CRUD (GET, POST, PUT, DELETE) para cualquier tabla
def crear_crud(
    prefijo: str,
    etiqueta: str,
    singular: str,
    Modelo: type,
    EsquemaIn: type[BaseModel],
    EsquemaOut: type[BaseModel]
):

    router = APIRouter(
        prefix=prefijo,
        tags=[etiqueta]
    )

    def guardar(db: Session):
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Conflicto: registro duplicado, "
                    "clave foranea inexistente o registro en uso"
                )
            )

    def buscar(db: Session, item_id: int):
        obj = db.get(Modelo, item_id)

        if obj is None:
            raise HTTPException(
                status_code=404,
                detail=f"{singular} no encontrado"
            )

        return obj

    @router.post(
        "/",
        response_model=EsquemaOut,
        status_code=201,
        summary=f"Crear {singular}"
    )
    def crear(datos: EsquemaIn, db: Session = Depends(get_db)):
        obj = Modelo(**datos.model_dump())
        db.add(obj)
        guardar(db)
        db.refresh(obj)
        return obj

    @router.get(
        "/",
        response_model=list[EsquemaOut],
        summary=f"Listar {etiqueta.capitalize()}"
    )
    def listar(db: Session = Depends(get_db)):
        return db.query(Modelo).order_by(Modelo.id).all()

    @router.get(
        "/{item_id}",
        response_model=EsquemaOut,
        summary=f"Obtener {singular}"
    )
    def obtener(item_id: int, db: Session = Depends(get_db)):
        return buscar(db, item_id)

    @router.put(
        "/{item_id}",
        response_model=EsquemaOut,
        summary=f"Actualizar {singular}"
    )
    def actualizar(
        item_id: int,
        datos: EsquemaIn,
        db: Session = Depends(get_db)
    ):
        obj = buscar(db, item_id)

        for campo, valor in datos.model_dump().items():
            setattr(obj, campo, valor)

        guardar(db)
        db.refresh(obj)
        return obj

    @router.delete(
        "/{item_id}",
        status_code=204,
        summary=f"Eliminar {singular}"
    )
    def eliminar(item_id: int, db: Session = Depends(get_db)):
        obj = buscar(db, item_id)
        db.delete(obj)
        guardar(db)

    return router


# =====================================================
# 7. APLICACION FASTAPI
# =====================================================

app = FastAPI(
    title="CRUD Universidad - CDIA2",
    version="1.0"
)


@app.get("/", tags=["default"], summary="Inicio")
def inicio():
    return {
        "mensaje": "Sistema Academico funcionando"
    }


app.include_router(
    crear_crud(
        "/usuarios",
        "usuarios",
        "Usuario",
        Usuario,
        UsuarioIn,
        UsuarioOut
    )
)

app.include_router(
    crear_crud(
        "/materias",
        "materias",
        "Materia",
        Materia,
        MateriaIn,
        MateriaOut
    )
)

app.include_router(
    crear_crud(
        "/paralelos",
        "paralelos",
        "Paralelo",
        Paralelo,
        ParaleloIn,
        ParaleloOut
    )
)


# =====================================================
# 8. USUARIOS DE UN PARALELO
# =====================================================

@app.get(
    "/paralelos/{paralelo_id}/usuarios",
    response_model=List[UsuarioOut],
    tags=["paralelos"],
    summary="Listar usuarios de un paralelo"
)
def usuarios_del_paralelo(
    paralelo_id: int,
    db: Session = Depends(get_db)
):
    paralelo = db.get(Paralelo, paralelo_id)

    if paralelo is None:
        raise HTTPException(
            status_code=404,
            detail="Paralelo no encontrado"
        )

    return paralelo.usuarios


# =====================================================
# 9. DATOS INICIALES
# =====================================================

MATERIAS = [
    "Programación 1",
    "Análisis 2",
    "Probabilidad y Estadística",
    "Base de Datos 1",
    "Historia de la Ciencia de Datos e Inteligencia Artificial",
    "Álgebra Lineal 1",
]

PARALELOS = [
    ("CDIA2-1", 1),
    ("CDIA2-2", 2),
    ("CDIA2-3", 3),
]

USUARIOS = [
    ("Carlos", "Mendoza", 20, "M", 1),
    ("Lucía", "Fernández", 19, "F", 1),
    ("Andrés", "Rojas", 21, "M", 1),
    ("Valeria", "Quispe", 20, "F", 1),
    ("Diego", "Vargas", 22, "M", 1),
    ("Camila", "Flores", 19, "F", 1),
    ("Mateo", "Gutiérrez", 20, "M", 1),
    ("Sofía", "Ramírez", 21, "F", 2),
    ("Javier", "Castro", 23, "M", 2),
    ("Daniela", "Torres", 19, "F", 2),
    ("Sebastián", "Morales", 20, "M", 2),
    ("Isabella", "Herrera", 22, "F", 2),
    ("Nicolás", "Salazar", 21, "M", 2),
    ("Paola", "Mamani", 20, "F", 2),
    ("Gabriel", "Cruz", 19, "M", 3),
    ("Fernanda", "Ortiz", 21, "F", 3),
    ("Alejandro", "Paredes", 22, "M", 3),
    ("Mariana", "Delgado", 20, "F", 3),
    ("Rodrigo", "Suárez", 23, "M", 3),
    ("Andrea", "Navarro", 19, "F", 3),
]


# =====================================================
# 10. CREAR TABLAS Y CARGAR DATOS
# =====================================================

@app.on_event("startup")
def iniciar():
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.query(Materia).count() == 0:
            db.add_all([
                Materia(nombre=nombre)
                for nombre in MATERIAS
            ])
            db.flush()

            db.add_all([
                Paralelo(nombre=nombre, materia_guia_id=materia_id)
                for nombre, materia_id in PARALELOS
            ])
            db.flush()

            db.add_all([
                Usuario(
                    nombre=nombre,
                    apellido=apellido,
                    edad=edad,
                    genero=genero,
                    paralelo_id=paralelo_id
                )
                for nombre, apellido, edad, genero, paralelo_id
                in USUARIOS
            ])

            db.commit()
