import requests
import random
from datetime import date
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
API_BASE_URL = "http://127.0.0.1:8000/api"
INICIO_JORNADA_HORAS = 8  # 08:00 AM será nuestro minuto 0
FIN_JORNADA_MINUTOS = 600 # 10 horas de jornada laboral

def minutos_desde_inicio(hora_str):
    """Convierte un string 'HH:MM' a minutos desde el inicio de la jornada."""
    if not hora_str:
        return None
    h, m = map(int, hora_str.split(':'))
    minutos_totales = (h * 60 + m) - (INICIO_JORNADA_HORAS * 60)
    return max(0, minutos_totales)

# =============================================================================
# 1. EXTRACCIÓN DE DATOS (CLIENTE API)
# =============================================================================
def obtener_datos_operativos():
    hoy = date.today().isoformat()
    
    print("1. Consumiendo API externa...")
    # Obtener técnicos
    tecnicos_req = requests.get(f"{API_BASE_URL}/tecnicos").json()
    
    # Obtener disponibilidad de hoy
    disp_req = requests.get(f"{API_BASE_URL}/disponibilidad?fecha={hoy}").json()
    ids_disponibles = [d["tecnico_id"] for d in disp_req if d["disponible"]]
    
    # Filtrar solo técnicos disponibles hoy
    tecnicos_hoy = [t for t in tecnicos_req if t["id"] in ids_disponibles]
    
    # Obtener OTs pendientes de asignar
    ordenes_pendientes = requests.get(f"{API_BASE_URL}/ordenes?estado=por_asignar").json()
    
    print(f"   -> Encontrados {len(tecnicos_hoy)} técnicos disponibles hoy.")
    print(f"   -> Encontradas {len(ordenes_pendientes)} OTs 'por_asignar'.")
    
    return tecnicos_hoy, ordenes_pendientes

# =============================================================================
# 2. TRANSFORMACIÓN PARA OR-TOOLS
# =============================================================================
def preparar_modelo_datos(tecnicos, ordenes):
    print("\n2. Transformando datos para OR-Tools...")
    data = {}
    
    data['num_vehicles'] = len(tecnicos)
    data['depot'] = 0 # El nodo 0 será nuestro punto de partida virtual
    
    num_nodos = len(ordenes) + 1 # +1 por el depósito

    # MOCK: Generar matriz de distancias y matriz de tiempos de viaje.
    # En producción esto debe ser reemplazado por llamadas a APIs de distancias/tiempos.
    matriz_distancias = [[0]*num_nodos for _ in range(num_nodos)]
    matriz_tiempos = [[0]*num_nodos for _ in range(num_nodos)]
    for i in range(num_nodos):
        for j in range(i+1, num_nodos):
            distancia = random.randint(1000, 15000)
            tiempo = random.randint(10, 90)  # Tiempo en minutos entre nodos ficticios
            matriz_distancias[i][j] = distancia
            matriz_distancias[j][i] = distancia
            matriz_tiempos[i][j] = tiempo
            matriz_tiempos[j][i] = tiempo
    data['distance_matrix'] = matriz_distancias
    data['time_matrix'] = matriz_tiempos

    # Demanda por OT y capacidad de cada técnico
    data['demands'] = [0] + [1] * len(ordenes)
    data['vehicle_capacities'] = [9 if t['tipo'] == 'externo' else len(ordenes) for t in tecnicos]

    # Sector para cada OT (extraído de la dirección)
    def sector_de_orden(ot):
        direccion = ot.get('direccion_instalacion', '')
        partes = [p.strip() for p in direccion.split(',') if p.strip()]
        return partes[-2] if len(partes) >= 2 else 'desconocido'

    orden_sectores = [sector_de_orden(ot) for ot in ordenes]
    sector_counts = {}
    for sector in orden_sectores:
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    data['orden_sectores'] = orden_sectores
    data['sector_counts'] = sector_counts

    # Transformar Ventanas de Tiempo
    # Nodo 0 (Depósito): Disponibilidad total de la jornada
    data['time_windows'] = [(0, FIN_JORNADA_MINUTOS)] 
    
    for ot in ordenes:
        minuto_programado = minutos_desde_inicio(ot.get('hora_programada'))
        if minuto_programado is not None:
            # Ventana estricta: +/- 30 minutos desde la hora programada
            inicio = max(0, minuto_programado - 30)
            fin = min(FIN_JORNADA_MINUTOS, minuto_programado + 30)
            data['time_windows'].append((inicio, fin))
        else:
            # Si no tiene hora, puede hacerse en cualquier momento de la jornada
            data['time_windows'].append((0, FIN_JORNADA_MINUTOS))

    return data

# =============================================================================
# 3. EJECUCIÓN DEL ALGORITMO (VRPTW)
# =============================================================================
def resolver_rutas(data, tecnicos):
    print("\n3. Ejecutando motor de optimización OR-Tools...")
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']),
                                           data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    time = 'Time'
    routing.AddDimension(
        time_callback_index,
        30,  # Espera máxima permitida
        FIN_JORNADA_MINUTOS, # Máximo tiempo por vehículo
        False,
        time)
    time_dimension = routing.GetDimensionOrDie(time)

    for location_idx, time_window in enumerate(data['time_windows']):
        if location_idx == data['depot']:
            continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])

    # Añadir capacidad por técnico: max 9 OTs para externos, internos sin límite práctico
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        data['vehicle_capacities'],
        True,
        'Capacity')

    # Forzar técnicos internos en sectores con más de 10 OTs
    external_vehicles = [idx for idx, t in enumerate(tecnicos) if t['tipo'] == 'externo']
    internal_vehicles = [idx for idx, t in enumerate(tecnicos) if t['tipo'] == 'interno']
    for node_idx, sector in enumerate(data['orden_sectores'], start=1):
        if data['sector_counts'].get(sector, 0) > 10:
            index = manager.NodeToIndex(node_idx)
            routing.SetAllowedVehiclesForIndex(internal_vehicles, index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    search_parameters.log_search = True

    solution = routing.SolveWithParameters(search_parameters)
    return manager, routing, solution

# =============================================================================
# DEBUG E INTEGRIDAD
# =============================================================================

def imprimir_diagnostico_infeasible(data, tecnicos, ordenes):
    """Imprime diagnósticos detallados cuando OR-Tools no encuentra solución."""
    print("   -> Diagnóstico de infeasibilidad:")
    print(f"      - Vehículos disponibles: {data['num_vehicles']}")
    print(f"      - OTs a resolver: {len(ordenes)}")
    print(f"      - Horizonte de jornada: 0 a {FIN_JORNADA_MINUTOS} minutos")

    estrictas = 0
    for idx, time_window in enumerate(data['time_windows'][1:], start=1):
        if time_window != (0, FIN_JORNADA_MINUTOS):
            estrictas += 1
    print(f"      - Ventanas de tiempo estrictas: {estrictas}/{len(ordenes)}")

    if estrictas > 0:
        print("      - Detalle de ventanas de tiempo para OTs con hora programada:")
        for idx, ot in enumerate(ordenes, start=1):
            window = data['time_windows'][idx]
            if window != (0, FIN_JORNADA_MINUTOS):
                print(
                    f"         * {ot['id']} -> {ot.get('hora_programada')} "
                    f"window=[{window[0]},{window[1]}]"
                )

    infeasibles = [
        (idx, w) for idx, w in enumerate(data['time_windows'][1:], start=1)
        if w[1] < w[0]
    ]
    if infeasibles:
        print("      - Ventanas de tiempo inválidas detectadas:")
        for idx, window in infeasibles:
            print(f"         * Nodo {idx} -> window={window}")

    print("      - Primeros 5 tiempos de viaje entre nodos (minutos):")
    for i in range(min(5, len(data['time_matrix']))):
        row = data['time_matrix'][i][:min(5, len(data['time_matrix']))]
        print(f"         {row}")

    if data['num_vehicles'] == 0:
        print("      - No hay técnicos disponibles hoy.")
    elif len(ordenes) == 0:
        print("      - No hay órdenes por asignar hoy.")
    else:
        print("      - Es posible que las ventanas de tiempo y los tiempos de viaje sean demasiado estrictos para la jornada actual.")

# =============================================================================
# 4. CARGA DE RESULTADOS (ENVIAR ASIGNACIONES A LA API)
# =============================================================================
def enviar_asignaciones(manager, routing, solution, tecnicos, ordenes, data):
    print("\n4. Procesando solución y enviando a la API...")
    if not solution:
        print("   -> No se encontró una solución matemática factible.")
        imprimir_diagnostico_infeasible(data, tecnicos, ordenes)
        return

    for vehicle_id in range(len(tecnicos)):
        tecnico_actual = tecnicos[vehicle_id]
        index = routing.Start(vehicle_id)
        
        rutas_asignadas = []
        # Recorremos la ruta ignorando el nodo 0 (depósito virtual de inicio)
        while not routing.IsEnd(index):
            nodo_real = manager.IndexToNode(index)
            if nodo_real != 0:
                ot_correspondiente = ordenes[nodo_real - 1] # -1 porque el 0 era el depósito
                rutas_asignadas.append(ot_correspondiente['id'])
            
            index = solution.Value(routing.NextVar(index))
            
        if rutas_asignadas:
            print(f"   -> Técnico {tecnico_actual['nombre']} {tecnico_actual['apellidos']} ({tecnico_actual['tipo']}):")
            print(f"      OTs asignadas: {rutas_asignadas}")
            
            # Impactar en la API (PATCH)
            for ot_id in rutas_asignadas:
                payload = {"tecnico_id": tecnico_actual['id']}
                url = f"{API_BASE_URL}/ordenes/{ot_id}/tecnico"
                res = requests.patch(url, json=payload)
                
                if res.status_code == 200:
                    print(f"        [OK] OT {ot_id} vinculada exitosamente en el Backoffice.")
                else:
                    print(f"        [ERROR] Falló la asignación para {ot_id}: {res.text}")
        else:
            print(f"   -> Técnico {tecnico_actual['nombre']}: Sin asignaciones en esta ronda.")

# =============================================================================
# FLUJO PRINCIPAL
# =============================================================================
if __name__ == '__main__':
    # 1. Extraer
    tecnicos, ordenes = obtener_datos_operativos()
    
    if not tecnicos or not ordenes:
        print("No hay suficientes datos (técnicos disponibles u OTs) para optimizar hoy.")
    else:
        # 2. Transformar
        data_model = preparar_modelo_datos(tecnicos, ordenes)
        
        # 3. Optimizar
        manager, routing, solution = resolver_rutas(data_model, tecnicos)
        
        # 4. Cargar
        enviar_asignaciones(manager, routing, solution, tecnicos, ordenes, data_model)
        print("\n¡Proceso de asignación finalizado!")