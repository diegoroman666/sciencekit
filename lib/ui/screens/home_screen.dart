import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

// Importamos la lógica de datos
import '../../logic/data_provider.dart';

// Importamos todas las pantallas funcionales
import 'charts_screen.dart';
import 'stats_screen.dart';
import 'prediction_screen.dart';
import 'probability_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    // Accedemos al estado global de la aplicación
    final dataProvider = Provider.of<DataProvider>(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text("Data Master Elite"),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // --- SECCIÓN 1: CABECERA Y CARGA DE ARCHIVOS ---
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF2D2D44), // Color estilo tarjeta oscura
                borderRadius: BorderRadius.circular(15),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.2),
                    blurRadius: 10,
                    offset: const Offset(0, 5),
                  ),
                ],
              ),
              child: Column(
                children: [
                  Icon(
                    Icons.analytics_outlined,
                    size: 60,
                    color: Theme.of(context).primaryColor,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    dataProvider.fileName ??
                        "Adjunte un archivo Excel (.xlsx) o CSV",
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 5),
                  if (dataProvider.columns.isNotEmpty)
                    Text(
                      "${dataProvider.columns.length} Columnas detectadas",
                      style: const TextStyle(color: Colors.grey, fontSize: 12),
                    ),
                  const SizedBox(height: 15),
                  ElevatedButton.icon(
                    onPressed: () => dataProvider.pickAndProcessFile(),
                    icon: const Icon(Icons.upload_file),
                    label: Text(
                      dataProvider.fileName == null
                          ? "Cargar Dataset"
                          : "Cambiar Archivo",
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4E54C8),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 30,
                        vertical: 15,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 25),

            // --- SECCIÓN 2: ESTADO DE CARGA O MENÚ PRINCIPAL ---
            if (dataProvider.isLoading)
              const Expanded(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 15),
                      Text(
                        "Procesando minería de datos...",
                        style: TextStyle(color: Colors.white70),
                      ),
                    ],
                  ),
                ),
              )
            else if (dataProvider.columns.isEmpty)
              const Expanded(
                child: Center(
                  child: Text(
                    "Esperando datos para comenzar el análisis...",
                    style: TextStyle(
                      color: Colors.white38,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              )
            else
              // --- SECCIÓN 3: GRID DE BOTONES (LOS 4 MÓDULOS) ---
              Expanded(
                child: GridView.count(
                  crossAxisCount: 2, // 2 columnas
                  crossAxisSpacing: 15,
                  mainAxisSpacing: 15,
                  childAspectRatio:
                      1.1, // Relación de aspecto para que sean cuadraditos
                  children: [
                    // BOTÓN 1: GRÁFICOS
                    _MenuButton(
                      title: "Generador de\nGráficos",
                      icon: Icons.pie_chart,
                      color: Colors.blueAccent,
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const ChartsScreen()),
                      ),
                    ),

                    // BOTÓN 2: PREDICCIÓN (Asesoría)
                    _MenuButton(
                      title: "Asesoría &\nPredicción (AI)",
                      icon: Icons.trending_up,
                      color: Colors.greenAccent.shade700,
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const PredictionScreen(),
                        ),
                      ),
                    ),

                    // BOTÓN 3: ESTADÍSTICA DESCRIPTIVA
                    _MenuButton(
                      title: "Datos\nEstadísticos",
                      icon: Icons.table_chart,
                      color: Colors.orangeAccent,
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const StatsScreen()),
                      ),
                    ),

                    // BOTÓN 4: PROBABILIDAD
                    _MenuButton(
                      title: "Datos\nProbabilísticos",
                      icon: Icons.casino,
                      color: Colors.purpleAccent,
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const ProbabilityScreen(),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// Widget auxiliar para diseño consistente de los botones del menú
class _MenuButton extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _MenuButton({
    required this.title,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF2D2D44),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.1),
              blurRadius: 8,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.2),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 32, color: color),
            ),
            const SizedBox(height: 12),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
