import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:excel/excel.dart';
import 'package:csv/csv.dart';
import 'package:flutter/material.dart';
import '../models/dataset_model.dart';

class DataProvider with ChangeNotifier {
  List<DataColumnModel> columns = [];
  String? fileName;
  bool isLoading = false;

  // Cargar Archivo
  Future<void> pickAndProcessFile() async {
    FilePickerResult? result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['csv', 'xlsx'],
    );

    if (result != null) {
      isLoading = true;
      notifyListeners();

      File file = File(result.files.single.path!);
      fileName = result.files.single.name;

      if (fileName!.endsWith('.csv')) {
        await _processCSV(file);
      } else {
        await _processExcel(file);
      }

      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _processExcel(File file) async {
    var bytes = file.readAsBytesSync();
    var excel = Excel.decodeBytes(bytes);
    // Tomamos la primera hoja
    var sheet = excel.tables[excel.tables.keys.first];

    if (sheet != null) {
      List<List<dynamic>> rows = [];
      for (var row in sheet.rows) {
        rows.add(row.map((e) => e?.value).toList());
      }
      _parseData(rows);
    }
  }

  Future<void> _processCSV(File file) async {
    final input = file.readAsStringSync();
    List<List<dynamic>> rows = const CsvToListConverter().convert(input);
    _parseData(rows);
  }

  // Detectar tipos y crear columnas
  void _parseData(List<List<dynamic>> rawData) {
    columns.clear();
    if (rawData.isEmpty) return;

    List<String> headers = rawData[0].map((e) => e.toString()).toList();

    // Inicializar columnas
    for (int i = 0; i < headers.length; i++) {
      List<dynamic> colValues = [];
      bool isQuant = true;

      for (int j = 1; j < rawData.length; j++) {
        var val = rawData[j][i];

        // Intentar parsear a numero
        if (val == null || val.toString().trim().isEmpty) {
          // Manejo de nulos (puedes decidir ignorar o poner 0)
        } else {
          double? numVal = double.tryParse(val.toString());
          if (numVal == null) {
            isQuant = false; // Encontró texto, entonces es cualitativa
            colValues.add(val.toString());
          } else {
            colValues.add(numVal);
          }
        }
      }

      columns.add(
        DataColumnModel(
          name: headers[i],
          values: colValues,
          type: isQuant ? DataType.quantitative : DataType.qualitative,
        ),
      );
    }
  }

  // --- MÉTODOS ESTADÍSTICOS BÁSICOS ---

  // Obtener estadísticas descriptivas de una columna
  Map<String, double> getDescriptiveStats(String colName) {
    var col = columns.firstWhere((c) => c.name == colName);
    if (!col.isNumeric) {
      throw Exception(
        "No se pueden calcular estadísticas de datos cualitativos",
      );
    }

    List<double> data = col.values.cast<double>()..sort();

    double sum = data.reduce((a, b) => a + b);
    double mean = sum / data.length;
    double median = data.length % 2 == 1
        ? data[data.length ~/ 2]
        : (data[data.length ~/ 2 - 1] + data[data.length ~/ 2]) / 2;

    return {
      "Media": mean,
      "Mediana": median,
      "Mínimo": data.first,
      "Máximo": data.last,
      "Total Datos": data.length.toDouble(),
    };
  }

  // Tabla de Frecuencias
  Map<dynamic, int> getFrequencyTable(String colName) {
    var col = columns.firstWhere((c) => c.name == colName);
    var map = <dynamic, int>{};
    for (var element in col.values) {
      map[element] = (map[element] ?? 0) + 1;
    }
    return map;
  }
}
