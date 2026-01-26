enum DataType { quantitative, qualitative }

class DataColumnModel {
  final String name;
  final List<dynamic> values;
  final DataType type;

  DataColumnModel({
    required this.name,
    required this.values,
    required this.type,
  });

  // Helper para saber si es numérico
  bool get isNumeric => type == DataType.quantitative;
}
