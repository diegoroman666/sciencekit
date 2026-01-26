import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../logic/data_provider.dart';

class ChartsScreen extends StatefulWidget {
  const ChartsScreen({super.key});

  @override
  State<ChartsScreen> createState() => _ChartsScreenState();
}

class _ChartsScreenState extends State<ChartsScreen> {
  String? selectedX;
  String? selectedY;
  String chartType = 'Dispersión'; // Dispersión, Barras

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<DataProvider>(context);

    // Obtener nombres de columnas
    final options = provider.columns.map((e) => e.name).toList();

    return Scaffold(
      appBar: AppBar(title: const Text("Generador de Gráficos")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // Controles
            Row(
              children: [
                Expanded(
                  child: DropdownButton<String>(
                    value: selectedX,
                    hint: const Text("Eje X"),
                    isExpanded: true,
                    items: options
                        .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                        .toList(),
                    onChanged: (v) => setState(() => selectedX = v),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: DropdownButton<String>(
                    value: selectedY,
                    hint: const Text("Eje Y"),
                    isExpanded: true,
                    items: options
                        .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                        .toList(),
                    onChanged: (v) => setState(() => selectedY = v),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            // Área de Gráfico
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.white10,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: selectedX != null && selectedY != null
                    ? _buildChart(provider)
                    : const Center(
                        child: Text("Seleccione variables para graficar"),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChart(DataProvider provider) {
    // Lógica simple para Scatter Plot
    var colX = provider.columns.firstWhere((c) => c.name == selectedX);
    var colY = provider.columns.firstWhere((c) => c.name == selectedY);

    if (!colX.isNumeric || !colY.isNumeric) {
      return const Center(
        child: Text(
          "Para dispersión ambas variables deben ser numéricas (Cuantitativas)",
        ),
      );
    }

    List<FlSpot> spots = [];
    for (int i = 0; i < colX.values.length; i++) {
      spots.add(
        FlSpot(
          (colX.values[i] as num).toDouble(),
          (colY.values[i] as num).toDouble(),
        ),
      );
    }

    return LineChart(
      LineChartData(
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: false,
            dotData: const FlDotData(show: true), // Mostrar puntos
            color: Colors.blue,
            barWidth: 0, // Solo puntos para scatter
          ),
        ],
        titlesData: FlTitlesData(
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(showTitles: true, reservedSize: 30),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(showTitles: true, reservedSize: 40),
          ),
        ),
      ),
    );
  }
}
