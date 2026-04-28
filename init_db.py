from app import app, db, SystemState, Elephant, ElephantSnapshot, WarehouseSnapshot
from datetime import date

def init_database():
    with app.app_context():
        db.drop_all()
        db.create_all()

        today = date.today()
        state = SystemState(
            current_date=today, 
            max_simulated_date=today,
            grass_kg=5000.0, 
            branches_kg=5000.0
        )
        db.session.add(state)

        w_snap = WarehouseSnapshot(record_date=today, grass_kg=5000.0, branches_kg=5000.0)
        db.session.add(w_snap)
            
        starter_elephants = [
            Elephant(name="Дамбо", genus="Loxodonta", species="Саванный слон (Loxodonta africana)", birth_date=date(2015, 5, 10), admission_date=today, weight_kg=3500, is_healthy=True, dirt_level=0),
            Elephant(name="Бабар", genus="Elephas", species="Индийский слон", birth_date=date(1995, 8, 20), admission_date=today, weight_kg=4200, is_healthy=True, dirt_level=15),
        ]
        db.session.add_all(starter_elephants)
        db.session.flush()

        for e in starter_elephants:
            snap = ElephantSnapshot(
                elephant_id=e.id, record_date=today,
                weight_kg=e.weight_kg, is_healthy=e.is_healthy, dirt_level=e.dirt_level
            )
            db.session.add(snap)
            
        db.session.commit()
        print("База успешно пересоздана с поддержкой Snapshots!")

if __name__ == "__main__":
    init_database()