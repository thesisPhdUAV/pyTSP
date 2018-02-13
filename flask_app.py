from threading import Lock
from flask import Flask, render_template, request, session
from flask_socketio import emit, SocketIO
from json import dumps, load
from os.path import abspath, dirname, join
from sqlalchemy import exc as sql_exception
from sys import dont_write_bytecode, path

dont_write_bytecode = True
path_app = dirname(abspath(__file__))
if path_app not in path:
    path.append(path_app)

from database import db, create_database
from models import City

def configure_database(app):
    create_database()
    @app.teardown_request
    def shutdown_session(exception=None):
        db.session.remove()
    db.init_app(app)

def configure_socket(app):
    async_mode = None
    socketio = SocketIO(app, async_mode=async_mode)
    thread_lock = Lock()
    return socketio

def import_cities():
    with open(join(path_app, 'data', 'cities.json')) as data:    
        for city_dict in load(data):
            if int(city_dict['population']) < 800000:
                continue
            city = City(**city_dict)
            db.session.add(city)
        try:
            db.session.commit()
        except sql_exception.IntegrityError:
            db.session.rollback()

def create_app(config='config'):
    app = Flask(__name__)
    app.config.from_object('config')
    configure_database(app)
    socketio = configure_socket(app)
    from algorithms.pytsp import pyTSP
    tsp = pyTSP()
    import_cities()
    return app, socketio, tsp

app, socketio, tsp = create_app()

## Views

@app.route('/', methods = ['GET', 'POST'])
def algorithm():
    session['best'] = float('inf')
    session['crossover'], session['mutation'] = 'OC', 'Swap'
    view = request.form['view'] if 'view' in request.form else '2D'
    return render_template(
        'index.html',
        view = view,
        cities = {
            city.id: {
                property: getattr(city, property)
                for property in City.properties
                }
            for city in City.query.all()
            },
        async_mode = socketio.async_mode
        )

def socket_emit(method):
    @socketio.on(method)
    def function():
        tour = 'build_tours' #+ 's'*(method not in ('nearest_neighbor', 'ILP_solver'))
        session['best'] = float('inf')
        emit(tour, getattr(tsp, method)())
    return function
for algorithm in tsp.algorithms:
    socket_emit(algorithm)

@socketio.on('genetic_algorithm')
def genetic_algorithm(data):
    if 'generation' not in session:
        session['generation'] = tsp.create_first_generation()
    session['generation'], best, length = tsp.cycle(session['generation'], **data)
    if length < session['best']:
        session['best'] = length
        emit('best_solution', (best, length))
    else:
        emit('current_solution', (best, length))

if __name__ == '__main__':
    socketio.run(app)
