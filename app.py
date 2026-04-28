import os
import re
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'advanced-elephant-secret'
BASE_DIR = os.path.abspath(os.path.dirname(__name__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'elephants.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class SystemState(db.Model):
    """Глобальное состояние системы"""
    id = db.Column(db.Integer, primary_key=True)
    current_date = db.Column(db.Date, nullable=False, default=date.today)
    max_simulated_date = db.Column(db.Date, nullable=False, default=date.today)
    grass_kg = db.Column(db.Float, default=1000.0)
    branches_kg = db.Column(db.Float, default=1000.0)

class LogRecord(db.Model):
    """Логирование всех действий"""
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.Date, nullable=False)
    action = db.Column(db.String(255), nullable=False)

class Elephant(db.Model):
    """Модель слона (текущее состояние)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    genus = db.Column(db.String(50), nullable=False)
    species = db.Column(db.String(50), nullable=False)
    birth_date = db.Column(db.Date, nullable=False)
    admission_date = db.Column(db.Date, nullable=False)
    departure_date = db.Column(db.Date, nullable=True)
    weight_kg = db.Column(db.Integer, nullable=False)
    is_healthy = db.Column(db.Boolean, default=True)
    dirt_level = db.Column(db.Integer, default=0)

    def get_age(self, target_date: date) -> int:
        return target_date.year - self.birth_date.year - ((target_date.month, target_date.day) < (self.birth_date.month, self.birth_date.day))

    def get_food_consumption(self, target_date: date) -> dict:
        age = self.get_age(target_date)
        percent = 0.055 if age < 10 else 0.045
        total_food = self.weight_kg * percent
        if self.genus == 'Loxodonta':
            return {'grass': total_food * 0.4, 'branches': total_food * 0.6}
        return {'grass': total_food * 0.7, 'branches': total_food * 0.3}

class ElephantSnapshot(db.Model):
    """Слепок состояния слона в конкретный день (для правильной истории)"""
    id = db.Column(db.Integer, primary_key=True)
    elephant_id = db.Column(db.Integer, db.ForeignKey('elephant.id'), nullable=False)
    record_date = db.Column(db.Date, nullable=False)
    weight_kg = db.Column(db.Integer, nullable=False)
    is_healthy = db.Column(db.Boolean, nullable=False)
    dirt_level = db.Column(db.Integer, nullable=False)

class WarehouseSnapshot(db.Model):
    """Слепок состояния склада в конкретный день (история запасов еды)"""
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.Date, nullable=False, unique=True)
    grass_kg = db.Column(db.Float, nullable=False)
    branches_kg = db.Column(db.Float, nullable=False)

def add_log(message: str, log_date: date):
    log = LogRecord(log_date=log_date, action=message)
    db.session.add(log)

@app.route('/')
def index():
    state = SystemState.query.first()
    is_past = state.current_date < state.max_simulated_date
    next_day_date = state.current_date + timedelta(days=1)
    
    display_grass = state.grass_kg
    display_branches = state.branches_kg

    query = Elephant.query.filter(Elephant.admission_date <= state.current_date)
    query = query.filter((Elephant.departure_date == None) | (Elephant.departure_date > state.current_date))
    
    filter_genus = request.args.get('filter_genus')
    if filter_genus:
        query = query.filter(Elephant.genus == filter_genus)
        
    elephants_data = query.all()

    if is_past:
        w_snap = WarehouseSnapshot.query.filter_by(record_date=state.current_date).first()
        if w_snap:
            display_grass = w_snap.grass_kg
            display_branches = w_snap.branches_kg

        snapshots = ElephantSnapshot.query.filter_by(record_date=state.current_date).all()
        snap_map = {s.elephant_id: s for s in snapshots}
        for e in elephants_data:
            if e.id in snap_map:
                e.weight_kg = snap_map[e.id].weight_kg
                e.is_healthy = snap_map[e.id].is_healthy
                e.dirt_level = snap_map[e.id].dirt_level

    filter_health = request.args.get('filter_health')
    if filter_health == 'true':
        elephants_data = [e for e in elephants_data if e.is_healthy]
    elif filter_health == 'false':
        elephants_data = [e for e in elephants_data if not e.is_healthy]

    sort_by = request.args.get('sort', 'name')
    if sort_by == 'weight':
        elephants_data.sort(key=lambda e: e.weight_kg, reverse=True)
    elif sort_by == 'age':
        elephants_data.sort(key=lambda e: e.birth_date)
    elif sort_by == 'species':
        elephants_data.sort(key=lambda e: e.species)
    else:
        elephants_data.sort(key=lambda e: e.name)

    return render_template(
        'index.html', elephants=elephants_data, state=state, 
        is_past=is_past, next_day_date=next_day_date, current_sort=sort_by,
        current_filter_genus=filter_genus, current_filter_health=filter_health,
        display_grass=display_grass, display_branches=display_branches
    )

@app.route('/logs')
def view_logs():
    logs = LogRecord.query.order_by(LogRecord.log_date.desc(), LogRecord.id.desc()).all()
    return render_template('logs.html', logs=logs)

@app.route('/add', methods=['POST'])
def add_elephant():
    state = SystemState.query.first()
    name = request.form.get('name').strip()
    
    if not re.match(r"^[A-Za-zА-Яа-яЁё\s]+$", name):
        flash("Ошибка: Имя должно содержать только буквы!", "error")
        return redirect(url_for('index'))

    try:
        weight = int(request.form.get('weight_kg'))
        if weight > 12240:
            flash("Ошибка: Вес больше исторического максимума (12240 кг)!", "error")
            return redirect(url_for('index'))
            
        birth_date = date.fromisoformat(request.form.get('birth_date'))
        admission_date = date.fromisoformat(request.form.get('admission_date'))
        
        if admission_date > state.current_date:
            flash("Ошибка: Дата прибытия не может быть в будущем!", "error")
            return redirect(url_for('index'))
            
    except ValueError:
        flash("Ошибка в форматах чисел или дат!", "error")
        return redirect(url_for('index'))

    elephant = Elephant(
        name=name, genus=request.form.get('genus'), species=request.form.get('species'),
        birth_date=birth_date, admission_date=admission_date, weight_kg=weight
    )
    db.session.add(elephant)
    db.session.flush()

    days_past = (state.max_simulated_date - admission_date).days
    if days_past >= 0:
        can_add = True
        fail_date = None
        cumulative_grass = 0
        cumulative_branches = 0
        
        sim_date = admission_date
        while sim_date <= state.max_simulated_date:
            food = elephant.get_food_consumption(sim_date)
            cumulative_grass += food['grass']
            cumulative_branches += food['branches']
            
            w_snap = WarehouseSnapshot.query.filter_by(record_date=sim_date).first()
            if w_snap and (w_snap.grass_kg < cumulative_grass or w_snap.branches_kg < cumulative_branches):
                can_add = False
                fail_date = sim_date
                break
            sim_date += timedelta(days=1)
            
        if not can_add:
            db.session.rollback()
            flash(f"Невозможно добавить слона! В истории (на {fail_date}) не хватило бы еды. Переместитесь в прошлое и пополните склад.", "error")
            return redirect(url_for('index'))

        sim_date = admission_date
        t_grass, t_branches, dirt = 0, 0, 0
        
        while sim_date <= state.max_simulated_date:
            snap = ElephantSnapshot(
                elephant_id=elephant.id, record_date=sim_date,
                weight_kg=elephant.weight_kg, is_healthy=True, dirt_level=dirt
            )
            db.session.add(snap)
            
            food = elephant.get_food_consumption(sim_date)
            t_grass += food['grass']
            t_branches += food['branches']
            
            w_snap = WarehouseSnapshot.query.filter_by(record_date=sim_date).first()
            if w_snap:
                w_snap.grass_kg -= t_grass
                w_snap.branches_kg -= t_branches
            
            dirt = min(100, dirt + 5)
            sim_date += timedelta(days=1)

        state.grass_kg -= t_grass
        state.branches_kg -= t_branches
        elephant.dirt_level = dirt
        add_log(f"Слон {name} добавлен задним числом. Удержано за {days_past+1} дн: {t_grass:.1f}кг сена, {t_branches:.1f}кг веток.", state.current_date)
    
    db.session.commit()
    flash(f"Слон {name} успешно добавлен!", "success")
    return redirect(url_for('index'))

@app.route('/edit_weight/<int:e_id>', methods=['POST'])
def edit_weight(e_id):
    state = SystemState.query.first()
    if state.current_date < state.max_simulated_date:
        flash("Вы находитесь в режиме истории. Редактировать вес можно только в настоящем!", "error")
        return redirect(url_for('index'))
        
    e = Elephant.query.get_or_404(e_id)
    new_weight = int(request.form.get('weight_kg'))
    
    if new_weight > 12240:
        flash("Вес не может превышать 12240 кг!", "error")
    else:
        e.weight_kg = new_weight
        snap = ElephantSnapshot.query.filter_by(elephant_id=e.id, record_date=state.current_date).first()
        if snap: snap.weight_kg = new_weight
        add_log(f"Изменен вес слона {e.name} на {new_weight} кг.", state.current_date)
        flash("Вес сохранен.", "success")
        
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/time_travel', methods=['POST'])
def time_travel():
    state = SystemState.query.first()
    target_date = date.fromisoformat(request.form.get('target_date'))

    if target_date <= state.max_simulated_date:
        state.current_date = target_date
        db.session.commit()
        flash(f"Просмотр истории на дату: {target_date}", "info")
        return redirect(url_for('index'))

    dry_run_date = state.max_simulated_date + timedelta(days=1)
    temp_grass = state.grass_kg
    temp_branches = state.branches_kg
    can_travel = True
    fail_date = None

    while dry_run_date <= target_date:
        active_elephants = Elephant.query.filter(Elephant.admission_date <= dry_run_date).filter((Elephant.departure_date == None) | (Elephant.departure_date > dry_run_date)).all()
        for e in active_elephants:
            food = e.get_food_consumption(dry_run_date)
            temp_grass -= food['grass']
            temp_branches -= food['branches']
            
        if temp_grass < 0 or temp_branches < 0:
            can_travel = False
            fail_date = dry_run_date
            break
        dry_run_date += timedelta(days=1)

    if not can_travel:
        flash(f"Перемещение отменено! Запасы истощатся {fail_date}. Пожалуйста, сделайте закупку.", "error")
        return redirect(url_for('index'))

    sim_date = state.max_simulated_date + timedelta(days=1)
    while sim_date <= target_date:
        daily_grass, daily_branches = 0, 0
        active_elephants = Elephant.query.filter(Elephant.admission_date <= sim_date).filter((Elephant.departure_date == None) | (Elephant.departure_date > sim_date)).all()
        
        for e in active_elephants:
            food = e.get_food_consumption(sim_date)
            daily_grass += food['grass']
            daily_branches += food['branches']
            
            e.dirt_level = min(100, e.dirt_level + 5)

            snap = ElephantSnapshot(
                elephant_id=e.id, record_date=sim_date,
                weight_kg=e.weight_kg, is_healthy=e.is_healthy, dirt_level=e.dirt_level
            )
            db.session.add(snap)

            if e.birth_date.month == sim_date.month and e.birth_date.day == sim_date.day:
                add_log(f"Слон {e.name} празднует день рождения! ({e.get_age(sim_date)} лет)", sim_date)

        state.grass_kg -= daily_grass
        state.branches_kg -= daily_branches

        w_snap = WarehouseSnapshot(record_date=sim_date, grass_kg=state.grass_kg, branches_kg=state.branches_kg)
        db.session.add(w_snap)

        if daily_grass > 0 or daily_branches > 0:
            add_log(f"Потребление еды за день: {daily_grass:.1f} кг сена, {daily_branches:.1f} кг веток.", sim_date)
        
        sim_date += timedelta(days=1)

    state.max_simulated_date = target_date
    state.current_date = target_date
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_food', methods=['POST'])
def add_food():
    state = SystemState.query.first()
    grass = float(request.form.get('grass') or 0)
    branches = float(request.form.get('branches') or 0)
    
    state.grass_kg += grass
    state.branches_kg += branches

    sim_date = state.current_date
    while sim_date <= state.max_simulated_date:
        w_snap = WarehouseSnapshot.query.filter_by(record_date=sim_date).first()
        if w_snap:
            w_snap.grass_kg += grass
            w_snap.branches_kg += branches
        sim_date += timedelta(days=1)
        
    add_log(f"Пополнение склада (на дату {state.current_date}): Сено +{grass}кг, Ветки +{branches}кг", state.current_date)
    db.session.commit()
    flash("Запасы пополнены!", "success")
    return redirect(url_for('index'))

@app.route('/action/<int:e_id>/<action_type>', methods=['POST'])
def elephant_action(e_id, action_type):
    state = SystemState.query.first()
    if state.current_date < state.max_simulated_date:
        flash("Взаимодействия со слонами запрещены при просмотре истории!", "error")
        return redirect(url_for('index'))
        
    e = Elephant.query.get_or_404(e_id)
    snap = ElephantSnapshot.query.filter_by(elephant_id=e.id, record_date=state.current_date).first()

    if action_type == 'wash':
        e.dirt_level = 0
        if snap: snap.dirt_level = 0
        add_log(f"Слон {e.name} помыт.", state.current_date)
        flash(f"{e.name} теперь чистый!", "success")
    elif action_type == 'toggle_health':
        e.is_healthy = not e.is_healthy
        if snap: snap.is_healthy = e.is_healthy
        status = "выздоровел" if e.is_healthy else "заболел"
        add_log(f"Слон {e.name} изменил статус здоровья: {status}.", state.current_date)
    elif action_type == 'heaven':
        e.departure_date = state.current_date
        add_log(f"Слон {e.name} отправился в слоновий рай ☁️.", state.current_date)
        flash(f"{e.name} покинул нас...", "info")
        
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)