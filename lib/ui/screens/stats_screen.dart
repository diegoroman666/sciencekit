import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../logic/data_provider.dart';

class StatsScreen extends StatefulWidget {
  const StatsScreen({super.key});

  @override
  State<StatsScreen> createState() => _StatsScreenState();
}

class _StatsScreenState extends State<StatsScreen> {
  String? selectedCol;

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<DataProvider>(context);

    return Scaffold(
      appBar: AppBar(title: const Text("Datos Estadísticos")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            DropdownButton<String>(
              value: selectedCol,
              hint: const Text("Seleccione Variable de Estudio"),
              isExpanded: true,
              items: provider.columns
                  .map(
                    (e) => DropdownMenuItem(value: e.name, child: Text(e.name)),
                  )
                  .toList(),
              onChanged: (v) => setState(() => selectedCol = v),
            ),
            const SizedBox(height: 20),
            if (selectedCol != null)
              Expanded(child: _buildStatsView(provider, selectedCol!)),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsView(DataProvider provider, String colName) {
    var col = provider.columns.firstWhere((c) => c.name == colName);

    if (!col.isNumeric) {
      // TABLA DE FRECUENCIA PARA CUALITATIVAS
      var freqs = provider.getFrequencyTable(colName);
      return ListView(
        children: [
          const Text(
            "Variable Cualitativa detectada",
            style: TextStyle(color: Colors.orange),
          ),
          const SizedBox(height: 10),
          DataTable(
            columns: const [
              DataColumn(label: Text("Valor")),
              DataColumn(label: Text("Frecuencia")),
            ],
            rows: freqs.entries
                .map(
                  (e) => DataRow(
                    cells: [
                      DataCell(Text(e.key.toString())),
                      DataCell(Text(e.value.toString())),
                    ],
                  ),
                )
                .toList(),
          ),
        ],
      );
    } else {
      // ESTADÍSTICAS COMPLETAS PARA CUANTITATIVAS
      var stats = provider.getDescriptiveStats(colName);
      return ListView(
        children: [
          const Text(
            "Medidas de Tendencia Central y Dispersión",
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          ...stats.entries.map(
            (e) => Card(
              color: Colors.white10,
              child: ListTile(
                title: Text(e.key),
                trailing: Text(
                  e.value.toStringAsFixed(2),
                  style: const TextStyle(
                    fontSize: 20,
                    color: Colors.blueAccent,
                  ),
                ),
              ),
            ),
          ),
        ],
      );
    }
  }
}
