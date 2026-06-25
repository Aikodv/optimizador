import requests
import random
import time
from datetime import date
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# =============================================================================
# CONFIGURACION GENERAL
# =============================================================================
API_BASE_URL = "https://api-dummy-yurf.onrender.com/api"
INICIO_JORNADA_HORAS = 8  # 08:00 AM es el minuto 0
FIN_JORNADA_MINUTOS = 600 # 10 horas de jornada laboral

USAR_OSRM = True
OSRM_TABLE_URL = "http://router.project-osrm.org/table/v1/driving"
USAR_GEOCODING = True
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "optimizador-rutas-chile/3.0"

# Geocerca Chile (Bounding Box)
LAT_MIN, LAT_MAX = -56.5, -17.5
LON_MIN, LON_MAX = -75.6, -66.5

# Costos Algoritmicos
PENALTY_DROP_NODE = 10000000      # Costo por no hacer una OT
PENALTY_MIX_SECTOR = 999999999    # Costo prohibitivo para evitar que un interno cambie de sector

# =============================================================================
# FUNCIONES AUXILIARES (TIEMPO Y GEO)
# =============================================================================
def minutos_desde_inicio(hora_str):
    """Convierte 'HH:MM' a minutos desde el inicio de la jornada."""
    if not hora_str:
        return None
    try:
        h, m = map(int, hora_str.split(':'))
        minutos_totales = (h * 60 + m) - (INICIO_JORNADA_HORAS * 60)
        return max(0, minutos_totales)
    except ValueError:
        return None

def geocode_direccion(direccion):
    """Convierte una direccion a coordenadas forzando que caigan dentro de Chile."""
    try:
        params = {
            "q": direccion, 
            "format": "json", 
            "limit": 1, 
            "countrycodes": "cl", 
            "addressdetails": 0
        }
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "es"}
        res = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()
        
        if data:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            # Validacion estricta de Bounding Box para Chile
            if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                return lat, lon
            else:
                print(f"   [WARNING] Coordenadas descartadas (fuera de Chile): {lat}, {lon}")
    except requests.RequestException as e:
        print(f"   [WARNING] Fallo de red en Geocoding para '{direccion}': {e}")
    except (KeyError, IndexError, ValueError):
        pass
    
    return None, None

def asegurar_coordenadas_ordenes(ordenes):
    """Verifica y geocodifica de manera segura respetando la geocerca."""
    for ot in ordenes:
        if ot.get("latitud") is not None and ot.get("longitud") is not None:
            lat, lon = ot["latitud"], ot["longitud"]
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                ot["latitud"], ot["longitud"] = None, None
                print(f"   [WARNING] OT {ot.get('id')} con coordenadas API erroneas. Re-geocodificando...")

        if ot.get("latitud") is None:
            direccion = ot.get("direccion_instalacion")
            if not direccion:
                continue
            
            if USAR_GEOCODING:
                lat, lon = geocode_direccion(direccion)
                if lat is not None and lon is not None:
                    ot["latitud"], ot["longitud"] = lat, lon
                    print(f"   [INFO] OT {ot.get('id')} geocodificada en Chile: {lat},{lon}")
                    time.sleep(1)

def obtener_matrices_osrm(coords_nodos):
    """Obtiene la matriz completa de distancias y tiempos para todos los nodos."""
    num_nodos = len(coords_nodos)
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords_nodos])
    print(f"   [INFO] Solicitando matriz a OSRM para {num_nodos} puntos...")
    
    url = f"{OSRM_TABLE_URL}/{coords_str}?annotations=distance,duration"
    try:
        response = requests.get(url, timeout=15).json()
        if response.get('code') == 'Ok':
            matriz_tiempos = [[int(val // 60) for val in row] for row in response['durations']]
            matriz_distancias = [[int(val) for val in row] for row in response['distances']]
            return matriz_distancias, matriz_tiempos
        else:
            print(f"   [ERROR] OSRM fallo: {response.get('code')}. Usando MOCK.")
    except Exception as e:
        print(f"   [ERROR] Red OSRM: {e}. Usando MOCK.")
        
    m_dist = [[random.randint(1000, 15000) if i != j else 0 for j in range(num_nodos)] for i in range(num_nodos)]
    m_time = [[random.randint(10, 60) if i != j else 0 for j in range(num_nodos)] for i in range(num_nodos)]
    return m_dist, m_time

# =============================================================================
# 1. EXTRACCION (API) - SOLO LECTURA
# =============================================================================
def obtener_datos_operativos():
    print("1. Consumiendo API externa (LECTURA SOLAMENTE)...")
    hoy = date.today().isoformat()
    print(f"   Fecha de consulta: {hoy}")
    try:
        print(f"   [GET] {API_BASE_URL}/tecnicos")
        tecnicos_req = requests.get(f"{API_BASE_URL}/tecnicos").json()
        print(f"   [OK] {len(tecnicos_req)} tecnicos en total")
        
        print(f"   [GET] {API_BASE_URL}/disponibilidad?fecha={hoy}")
        disp_req = requests.get(f"{API_BASE_URL}/disponibilidad?fecha={hoy}").json()
        
        ids_disponibles = {d["tecnico_id"] for d in disp_req if d.get("disponible")}
        tecnicos_hoy = [t for t in tecnicos_req if t["id"] in ids_disponibles]
        
        print(f"   [GET] {API_BASE_URL}/ordenes?estado=por_asignar")
        ordenes_pendientes = requests.get(f"{API_BASE_URL}/ordenes?estado=por_asignar").json()
        
        print(f"\n   [RESUMEN DE CARGA]")
        print(f"   -> {len(tecnicos_hoy)} tecnicos disponibles (de {len(tecnicos_req)} totales)")
        internos = sum(1 for t in tecnicos_hoy if t.get('tipo') == 'interno')
        externos = len(tecnicos_hoy) - internos
        print(f"      - Internos: {internos} | Externos: {externos}")
        print(f"   -> {len(ordenes_pendientes)} OTs pendientes de asignacion")
        
        if tecnicos_hoy:
            print(f"\n   Tecnicos disponibles HOY:")
            for t in tecnicos_hoy[:5]:
                print(f"      - {t['nombre']} {t['apellidos']} (tipo: {t.get('tipo')}, zona: {t.get('zona')})")
            if len(tecnicos_hoy) > 5:
                print(f"      ... y {len(tecnicos_hoy) - 5} mas")
        
        return tecnicos_hoy, ordenes_pendientes
    except Exception as e:
        print(f"   [ERROR FATAL] Conexion a API: {e}")
        return [], []

# =============================================================================
# 2. TRANSFORMACION (MODELO)
# =============================================================================
def preparar_modelo_datos(tecnicos, ordenes):
    print("\n2. Transformando datos para el modelo VRP...")
    data = {}
    data['num_vehicles'] = len(tecnicos)
    V = data['num_vehicles']

    coords_nodos = [] # Guardara (lon, lat) de todos los nodos (Tecnicos + OTs)

    print(f"   [PROCESS] Geocodificando el punto de partida (zona) de {V} tecnicos...")
    for t in tecnicos:
        zona = t.get('zona', '')
        lat, lon = None, None
        if zona:
            # Añadimos "Chile" para evitar que busque la comuna en otro pais
            query = f"{zona}, Chile"
            lat, lon = geocode_direccion(query)
            
        if lat is None or lon is None:
            print(f"   [WARNING] No se encontro la zona '{zona}' del tecnico {t['nombre']}. Asignando punto central.")
            lat, lon = -33.4489, -70.6693 # Fallback Santiago Centro
            
        coords_nodos.append((lon, lat))
        print(f"      - Tecnico {t['nombre']}: Parte de {zona} ({lat}, {lon})")

    if USAR_GEOCODING:
        print(f"\n   [PROCESS] Geocodificando {len(ordenes)} OTs...")
        asegurar_coordenadas_ordenes(ordenes)

    for ot in ordenes:
        lat, lon = ot.get('latitud'), ot.get('longitud')
        if lat is None or lon is None:
            lat, lon = -33.4489, -70.6693
        coords_nodos.append((lon, lat))

    data['starts'] = list(range(V))
    data['ends'] = list(range(V))
    num_nodos = len(coords_nodos)

    print(f"   Total de vehiculos: {V}")
    print(f"   Total de nodos: {num_nodos} ({V} salidas de tecnicos + {len(ordenes)} OTs)")

    if USAR_OSRM and num_nodos <= 100:
        data['distance_matrix'], data['time_matrix'] = obtener_matrices_osrm(coords_nodos)
    else:
        print("   [INFO] Modo MOCK activado (OSRM deshabilitado o excede limite).")
        data['distance_matrix'] = [[random.randint(1000, 15000) if i != j else 0 for j in range(num_nodos)] for i in range(num_nodos)]
        data['time_matrix'] = [[random.randint(10, 60) if i != j else 0 for j in range(num_nodos)] for i in range(num_nodos)]

    # Demanda: 0 para nodos de salida de tecnicos, 1 para nodos de OTs
    data['demands'] = [0] * V + [1] * len(ordenes)
    data['vehicle_capacities'] = [9 if t.get('tipo') == 'externo' else len(ordenes) for t in tecnicos]
    data['tecnicos_info'] = [{'tipo': t.get('tipo'), 'zona': t.get('zona')} for t in tecnicos]

    def sector_de_orden(ot):
        direccion = ot.get('direccion_instalacion', '')
        partes = [p.strip() for p in direccion.split(',') if p.strip()]
        return partes[-2] if len(partes) >= 2 else f"desconocido-{ot['id']}"

    data['orden_sectores'] = [sector_de_orden(ot) for ot in ordenes]
    data['sector_counts'] = {}
    for sec in data['orden_sectores']:
        data['sector_counts'][sec] = data['sector_counts'].get(sec, 0) + 1

    print(f"\n   [RESUMEN] Distribucion por sector:")
    for sector, count in sorted(data['sector_counts'].items(), key=lambda x: x[1], reverse=True):
        restrict = " [SOLO INTERNOS]" if count >= 10 else ""
        print(f"      - {sector}: {count} OTs{restrict}")

    # Ventanas Temporales
    data['time_windows'] = [(0, FIN_JORNADA_MINUTOS)] * V
    for ot in ordenes:
        minuto_prog = minutos_desde_inicio(ot.get('hora_programada'))
        if minuto_prog is not None:
            data['time_windows'].append((max(0, minuto_prog - 30), min(FIN_JORNADA_MINUTOS, minuto_prog + 30)))
        else:
            data['time_windows'].append((0, FIN_JORNADA_MINUTOS))

    return data

def diagnosticar_orden_pendiente(ot, nodo_real, data, tecnicos):
    razones = []
    V = data['num_vehicles']
    idx_orden = nodo_real - V
    sector = data['orden_sectores'][idx_orden]
    time_window = data['time_windows'][nodo_real]
    count_sector = data['sector_counts'].get(sector, 0)

    if ot.get('latitud') is None or ot.get('longitud') is None:
        razones.append("Coordenadas invalidas o no encontradas en Chile. No se pudo enrutar.")
        return razones

    internal_techs = [t for t in tecnicos if t.get('tipo') == 'interno']
    if count_sector >= 10:
        if not internal_techs:
            razones.append(f"RESTRICCION SECTOR: '{sector}' tiene {count_sector} OTs. Requiere SOLO internos y NO HAY disponibles.")
        else:
            cap_internos = sum(data['vehicle_capacities'][i] for i, t in enumerate(tecnicos) if t.get('tipo') == 'interno')
            if count_sector > cap_internos:
                razones.append(f"RESTRICCION SECTOR: '{sector}' exige {count_sector} OTs, capacidad interna superada ({cap_internos}).")
            else:
                razones.append(f"RESTRICCION SECTOR: '{sector}' tiene {count_sector} OTs. No fue elegida en la solucion optima.")
        return razones

    travel_from_starts = [data['time_matrix'][v][nodo_real] for v in range(V)]
    min_travel = min(travel_from_starts) if travel_from_starts else 0
    if min_travel > time_window[1]:
        hora_prog = ot.get('hora_programada', 'N/A')
        razones.append(f"INVIABLE POR TIEMPO: Viaje mas corto desde un tecnico {min_travel} min > ventana maxima {time_window[1]} min (Hora prog: {hora_prog}).")

    total_ots = sum(data['demands'])
    total_capacity = sum(data['vehicle_capacities'])
    if total_ots > total_capacity:
        razones.append(f"EXCESO DE VOLUMEN: {total_ots} OTs vs capacidad flota {total_capacity}.")

    if not razones:
        razones.append("COLISION DE AGENDA / AISLAMIENTO: Colisiona con el recorrido o aisla geograficamente la ruta.")

    return razones

# =============================================================================
# 3. MOTOR VRP (OR-TOOLS)
# =============================================================================
def resolver_rutas(data, tecnicos):
    print("\n3. Ejecutando motor de optimizacion OR-Tools...")
    print(f"   [CONFIGURACION]")
    print(f"      - Vehiculos: {data['num_vehicles']}")
    print(f"      - Nodos Totales: {len(data['distance_matrix'])}")
    print(f"      - Estrategia: PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH")
    print(f"      - Tiempo limite: 5 segundos")
    
    manager = pywrapcp.RoutingIndexManager(
        len(data['distance_matrix']), 
        data['num_vehicles'], 
        data['starts'], 
        data['ends']
    )
    routing = pywrapcp.RoutingModel(manager)
    V = data['num_vehicles']

    def crear_callback_distancia(vehicle_id):
        def callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            
            tecnico = data['tecnicos_info'][vehicle_id]
            
            # Restriccion: Si es un viaje entre dos OTs (nodos >= V) y el tecnico es interno
            if from_node >= V and to_node >= V:
                if tecnico.get('tipo') == 'interno':
                    sector_from = data['orden_sectores'][from_node - V]
                    sector_to = data['orden_sectores'][to_node - V]
                    if sector_from != sector_to:
                        return PENALTY_MIX_SECTOR
            
            return data['distance_matrix'][from_node][to_node]
        return callback

    for vehicle_id in range(V):
        callback_idx = routing.RegisterTransitCallback(crear_callback_distancia(vehicle_id))
        routing.SetArcCostEvaluatorOfVehicle(callback_idx, vehicle_id)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node]
    
    time_callback_idx = routing.RegisterTransitCallback(time_callback)
    time_dimension_name = 'Time'
    routing.AddDimension(
        time_callback_idx,
        FIN_JORNADA_MINUTOS,  
        FIN_JORNADA_MINUTOS,  
        False, 
        time_dimension_name
    )
    time_dimension = routing.GetDimensionOrDie(time_dimension_name)

    # Restricciones Duras
    for node_idx, time_window in enumerate(data['time_windows']):
        if node_idx in data['starts'] or node_idx in data['ends']:
            continue
        index = manager.NodeToIndex(node_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])
        routing.AddDisjunction([index], PENALTY_DROP_NODE)

    def demand_callback(from_index):
        return data['demands'][manager.IndexToNode(from_index)]
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, data['vehicle_capacities'], True, 'Capacity'
    )

    internal_vehicles = [idx for idx, t in enumerate(tecnicos) if t.get('tipo') == 'interno']
    external_vehicles = [idx for idx, t in enumerate(tecnicos) if t.get('tipo') == 'externo']
    
    for i, sector in enumerate(data['orden_sectores']):
        node_idx = V + i
        if data['sector_counts'].get(sector, 0) >= 10:
            if internal_vehicles:
                index = manager.NodeToIndex(node_idx)
                for ext_v in external_vehicles:
                    routing.VehicleVar(index).RemoveValue(ext_v)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(5)
    search_parameters.log_search = False

    print(f"   [PROCESS] Buscando solucion optima...")
    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        print(f"   [OK] Solucion ENCONTRADA")
    else:
        print(f"   [WARNING] No se encontro solucion factible")
    
    return manager, routing, solution

# =============================================================================
# 4. ANALISIS Y REPORTE (SOLO LECTURA)
# =============================================================================
def enviar_asignaciones(manager, routing, solution, tecnicos, ordenes, data):
    print("\n4. Analizando y reportando resultados (LECTURA SOLAMENTE)...")
    
    if not solution:
        print("   [CRITICAL] No se encontro ninguna solucion matematica factible.")
        return

    V = data['num_vehicles']
    dropped_nodes = []
    
    for node in range(routing.Size()):
        if routing.IsStart(node) or routing.IsEnd(node):
            continue
        if solution.Value(routing.NextVar(node)) == node:
            nodo_real = manager.IndexToNode(node)
            idx_orden = nodo_real - V
            dropped_nodes.append(ordenes[idx_orden]['id'])
    
    print(f"\n   [RESUMEN DE ASIGNACION]")
    print(f"      - OTs asignadas: {len(ordenes) - len(dropped_nodes)} de {len(ordenes)}")
    print(f"      - OTs pendientes: {len(dropped_nodes)}")
    
    if dropped_nodes:
        print(f"\n   [DIAGNOSTICO DE {len(dropped_nodes)} OTs NO ASIGNABLES]")
        for ot_id in dropped_nodes:
            ot = next((orden for orden in ordenes if orden['id'] == ot_id), None)
            if ot is None:
                continue
            idx_orden = next((i for i, orden in enumerate(ordenes) if orden['id'] == ot_id), None)
            nodo_real = V + idx_orden
            
            razones = diagnosticar_orden_pendiente(ot, nodo_real, data, tecnicos)
            print(f"      [{ot_id}]")
            for razon in razones:
                print(f"        - {razon}")

    print(f"\n   [RUTAS PLANIFICADAS]")
    total_asignadas = 0
    for vehicle_id, tecnico_actual in enumerate(tecnicos):
        index = routing.Start(vehicle_id)
        rutas_asignadas = []
        
        while not routing.IsEnd(index):
            nodo_real = manager.IndexToNode(index)
            if nodo_real >= V:
                idx_orden = nodo_real - V
                rutas_asignadas.append(ordenes[idx_orden]['id'])
            index = solution.Value(routing.NextVar(index))
        
        total_asignadas += len(rutas_asignadas)
        
        if rutas_asignadas:
            capacidad = data['vehicle_capacities'][vehicle_id]
            uso = f"{len(rutas_asignadas)}/{capacidad}"
            print(f"      [OK] {tecnico_actual['nombre']} ({tecnico_actual.get('tipo')})")
            print(f"           Rutas: {rutas_asignadas} [Cap: {uso}]")
        else:
            print(f"      [EMPTY] {tecnico_actual['nombre']} ({tecnico_actual.get('tipo')}): Sin asignaciones")

# =============================================================================
# EJECUCION PRINCIPAL
# =============================================================================
if __name__ == '__main__':
    print("="*80)
    print("OPTIMIZADOR DE RUTAS - MODO LECTURA (Sin modificaciones en la API)")
    print("="*80)
    
    tecnicos, ordenes = obtener_datos_operativos()
    
    if not tecnicos or not ordenes:
        print("\n[FINALIZADO] Faltan tecnicos disponibles u OTs por asignar.")
    else:
        data_model = preparar_modelo_datos(tecnicos, ordenes)
        manager, routing, solution = resolver_rutas(data_model, tecnicos)
        enviar_asignaciones(manager, routing, solution, tecnicos, ordenes, data_model)
    
    print("\n" + "="*80)
    print("[SUCCESS] Proceso completado (NO se realizaron cambios en la API)")
    print("="*80)