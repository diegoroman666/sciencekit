import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../logic/data_provider.dart';
import '../../logic/math_utils.dart';

class PredictionScreen extends StatefulWidget {
  const PredictionScreen({super.key});

  @override
  State<PredictionScreen> createState() => _PredictionScreenState();
}

class _PredictionScreenState extends State<PredictionScreen> {
  String? selectedX; // Variable Independiente (Causa)
  String? selectedY; // Variable Dependiente (Efecto)

  final TextEditingController _inputController = TextEditingController();
  double? _predictionResult;
  Map<String, double>? _regressionModel;

  void _calculateModel(DataProvider provider) {
    if (selectedX == null || selectedY == null) return;

    var colX = provider.columns.firstWhere((c) => c.name == selectedX);
    var colY = provider.columns.firstWhere((c) => c.name == selectedY);

    // Validación estricta de tipos
    if (!colX.isNumeric || !colY.isNumeric) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "¡Error! La minería predictiva requiere variables Cuantitativas exclusivamente.",
          ),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    try {
      final xValues = colX.values.cast<double>();
      final yValues = colY.values.cast<double>();

      setState(() {
        _regressionModel = MathUtils.calculateLinearRegression(
          xValues,
          yValues,
        );
        _predictionResult = null; // Resetear predicción anterior
      });
    } catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text("Error matemático: $e")));
    }
  }

  void _predictValue() {
    if (_regressionModel == null || _inputController.text.isEmpty) return;
    double? inputVal = double.tryParse(_inputController.text);
    if (inputVal != null) {
      // y = mx + b
      double m = _regressionModel!['m']!;
      double b = _regressionModel!['b']!;
      setState(() {
        _predictionResult = (m * inputVal) + b;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<DataProvider>(context);
    final options = provider.columns.map((e) => e.name).toList();

    return Scaffold(
      appBar: AppBar(title: const Text("Asesoría & Predicción (AI)")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "Configuración del Modelo Predictivo",
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Colors.greenAccent,
              ),
            ),
            const SizedBox(height: 15),
            Row(
              children: [
                Expanded(
                  child: _buildDropdown(
                    "Var. Independiente (X)",
                    selectedX,
                    options,
                    (v) => selectedX = v,
                  ),
                ),
                const SizedBox(width: 15),
                Expanded(
                  child: _buildDropdown(
                    "Var. Dependiente (Y)",
                    selectedY,
                    options,
                    (v) => selectedY = v,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Center(
              child: ElevatedButton(
                onPressed: () => _calculateModel(provider),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.greenAccent.shade700,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 40,
                    vertical: 15,
                  ),
                ),
                child: const Text("Entrenar Modelo Lineal"),
              ),
            ),
            const SizedBox(height: 30),

            if (_regressionModel != null) ...[
              _buildModelResultsCard(),
              const SizedBox(height: 30),
              _buildPredictionSection(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildDropdown(
    String label,
    String? value,
    List<String> items,
    Function(String?) onChanged,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70)),
        DropdownButton<String>(
          value: value,
          isExpanded: true,
          dropdownColor: const Color(0xFF2D2D44),
          items: items
              .map((e) => DropdownMenuItem(value: e, child: Text(e)))
              .toList(),
          onChanged: (v) {
            setState(() {
              onChanged(v);
              _regressionModel = null;
            });
          },
        ),
      ],
    );
  }

  Widget _buildModelResultsCard() {
    double r2 = _regressionModel!['r2']!;
    String quality = r2 > 0.7 ? "Excelente" : (r2 > 0.4 ? "Moderada" : "Baja");
    Color qualityColor = r2 > 0.7
        ? Colors.green
        : (r2 > 0.4 ? Colors.orange : Colors.red);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF2D2D44),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          const Text(
            "Métricas del Modelo",
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const Divider(),
          Text(
            "Fórmula: y = ${_regressionModel!['m']!.toStringAsFixed(4)}x + ${_regressionModel!['b']!.toStringAsFixed(2)}",
            style: const TextStyle(fontFamily: 'Courier', fontSize: 16),
          ),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              Column(
                children: [
                  const Text("R² (Ajuste)"),
                  Text(
                    "${(r2 * 100).toStringAsFixed(2)}%",
                    style: TextStyle(
                      color: qualityColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ],
              ),
              Column(
                children: [
                  const Text("Correlación"),
                  Text(
                    _regressionModel!['r']!.toStringAsFixed(3),
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            "Interpretación: La capacidad del modelo para explicar la variabilidad es $quality.",
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white70,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPredictionSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          "Simulador & Prescripción",
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: Colors.blueAccent,
          ),
        ),
        const SizedBox(height: 15),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _inputController,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: "Ingrese valor para $selectedX",
                  border: const OutlineInputBorder(),
                  filled: true,
                  fillColor: Colors.white10,
                ),
              ),
            ),
            const SizedBox(width: 15),
            ElevatedButton(
              onPressed: _predictValue,
              child: const Text("Predecir"),
            ),
          ],
        ),
        if (_predictionResult != null) ...[
          const SizedBox(height: 20),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.blueAccent.shade700,
                  Colors.purpleAccent.shade700,
                ],
              ),
              borderRadius: BorderRadius.circular(15),
            ),
            child: Column(
              children: [
                const Text(
                  "Valor Predicho (Y)",
                  style: TextStyle(fontSize: 14, color: Colors.white70),
                ),
                Text(
                  _predictionResult!.toStringAsFixed(2),
                  style: const TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  "Asesoría Automática:",
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                Text(
                  "Basado en los datos históricos, si '$selectedX' aumenta a ${_inputController.text}, se proyecta que '$selectedY' alcance este valor. ${_regressionModel!['m']! > 0 ? 'Se observa una tendencia CRECIENTE.' : 'Se observa una tendencia DECRECIENTE.'}",
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}
