import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../logic/data_provider.dart';
import '../../logic/math_utils.dart';

class ProbabilityScreen extends StatefulWidget {
  const ProbabilityScreen({super.key});

  @override
  State<ProbabilityScreen> createState() => _ProbabilityScreenState();
}

class _ProbabilityScreenState extends State<ProbabilityScreen> {
  String? selectedCol;

  // Stats básicos de la variable seleccionada
  double? mean;
  double? stdDev;

  // Inputs para cálculo
  final TextEditingController _valAController = TextEditingController();
  final TextEditingController _valBController = TextEditingController();

  String calcType = 'P(X < a)'; // Tipos: P(X < a), P(X > a), P(a < X < b)
  double? probabilityResult;

  void _analyzeVariable(DataProvider provider) {
    if (selectedCol == null) return;

    var col = provider.columns.firstWhere((c) => c.name == selectedCol);
    if (!col.isNumeric) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Solo variables numéricas permitidas.")),
      );
      return;
    }

    List<double> values = col.values.cast<double>();
    setState(() {
      mean = MathUtils.calculateMean(values);
      stdDev = MathUtils.calculateStdDev(values);
      probabilityResult = null;
    });
  }

  void _calculateProbability() {
    if (mean == null || stdDev == null) return;

    double? a = double.tryParse(_valAController.text);
    double? b = double.tryParse(_valBController.text);

    double result = 0.0;

    if (calcType == 'P(X < a)' && a != null) {
      double z = (a - mean!) / stdDev!;
      result = MathUtils.normalCDF(z);
    } else if (calcType == 'P(X > a)' && a != null) {
      double z = (a - mean!) / stdDev!;
      result = 1.0 - MathUtils.normalCDF(z);
    } else if (calcType == 'P(a < X < b)' && a != null && b != null) {
      double zA = (a - mean!) / stdDev!;
      double zB = (b - mean!) / stdDev!;
      result = MathUtils.normalCDF(zB) - MathUtils.normalCDF(zA);
    }

    setState(() {
      probabilityResult = result;
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<DataProvider>(context);
    final options = provider.columns
        .where((c) => c.isNumeric)
        .map((e) => e.name)
        .toList();

    return Scaffold(
      appBar: AppBar(title: const Text("Calculadora Probabilística")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            const Text(
              "Análisis de Distribución Normal",
              style: TextStyle(fontSize: 18, color: Colors.purpleAccent),
            ),
            const SizedBox(height: 15),
            DropdownButton<String>(
              value: selectedCol,
              hint: const Text("Seleccione variable cuantitativa"),
              isExpanded: true,
              items: options
                  .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                  .toList(),
              onChanged: (v) {
                setState(() => selectedCol = v);
                _analyzeVariable(provider);
              },
            ),
            const SizedBox(height: 20),
            if (mean != null) ...[
              // Info Card
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _statChip("Media (μ)", mean!),
                  _statChip("Desv. Est (σ)", stdDev!),
                ],
              ),
              const Divider(height: 40),

              // Calculator Section
              const Text(
                "Calcular Probabilidad",
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 10),
              DropdownButton<String>(
                value: calcType,
                isExpanded: true,
                items: const [
                  DropdownMenuItem(
                    value: 'P(X < a)',
                    child: Text("Menor que 'a' (Cola Izquierda)"),
                  ),
                  DropdownMenuItem(
                    value: 'P(X > a)',
                    child: Text("Mayor que 'a' (Cola Derecha)"),
                  ),
                  DropdownMenuItem(
                    value: 'P(a < X < b)',
                    child: Text("Entre 'a' y 'b' (Intervalo)"),
                  ),
                ],
                onChanged: (v) => setState(() => calcType = v!),
              ),
              const SizedBox(height: 15),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _valAController,
                      decoration: const InputDecoration(
                        labelText: "Valor 'a'",
                        border: OutlineInputBorder(),
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  if (calcType == 'P(a < X < b)') ...[
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: _valBController,
                        decoration: const InputDecoration(
                          labelText: "Valor 'b'",
                          border: OutlineInputBorder(),
                        ),
                        keyboardType: TextInputType.number,
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: _calculateProbability,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.purpleAccent,
                  minimumSize: const Size(double.infinity, 50),
                ),
                child: const Text("Calcular Probabilidad"),
              ),

              if (probabilityResult != null) ...[
                const SizedBox(height: 30),
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: Colors.white10,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.purpleAccent),
                  ),
                  child: Column(
                    children: [
                      const Text(
                        "Probabilidad Resultante",
                        style: TextStyle(color: Colors.white70),
                      ),
                      Text(
                        "${(probabilityResult! * 100).toStringAsFixed(4)}%",
                        style: const TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _statChip(String label, double val) {
    return Column(
      children: [
        Text(label, style: const TextStyle(color: Colors.white54)),
        Text(
          val.toStringAsFixed(2),
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}
