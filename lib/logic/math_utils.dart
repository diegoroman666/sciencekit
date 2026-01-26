import 'dart:math';

class MathUtils {
  /// --- REGRESIÓN LINEAL SIMPLE ---
  /// Retorna un mapa con {m, b, r2, correlation}
  /// y = mx + b
  static Map<String, double> calculateLinearRegression(
    List<double> x,
    List<double> y,
  ) {
    if (x.length != y.length || x.isEmpty) {
      throw Exception(
        "Los conjuntos de datos deben tener el mismo tamaño y no estar vacíos.",
      );
    }

    int n = x.length;
    double sumX = x.reduce((a, b) => a + b);
    double sumY = y.reduce((a, b) => a + b);
    double sumXY = 0.0;
    double sumX2 = 0.0;
    double sumY2 = 0.0;

    for (int i = 0; i < n; i++) {
      sumXY += x[i] * y[i];
      sumX2 += x[i] * x[i];
      sumY2 += y[i] * y[i];
    }

    double numeratorSlope = (n * sumXY) - (sumX * sumY);
    double denominatorSlope = (n * sumX2) - (sumX * sumX);

    if (denominatorSlope == 0) return {}; // Evitar división por cero

    double m = numeratorSlope / denominatorSlope;
    double b = (sumY - (m * sumX)) / n;

    // Cálculo de Correlación (Pearson) y R^2
    double numeratorR = (n * sumXY) - (sumX * sumY);
    double denominatorR = sqrt(
      ((n * sumX2) - (sumX * sumX)) * ((n * sumY2) - (sumY * sumY)),
    );
    double r = numeratorR / denominatorR;
    double r2 = r * r;

    return {"m": m, "b": b, "r": r, "r2": r2};
  }

  /// --- ESTADÍSTICA PROBABILÍSTICA (Distribución Normal) ---

  // Media Aritmética
  static double calculateMean(List<double> data) {
    return data.reduce((a, b) => a + b) / data.length;
  }

  // Desviación Estándar (Poblacional)
  static double calculateStdDev(List<double> data) {
    double mean = calculateMean(data);
    double sumSquaredDiff = data
        .map((val) => pow(val - mean, 2).toDouble())
        .reduce((a, b) => a + b);
    return sqrt(sumSquaredDiff / data.length);
  }

  // Función de Distribución Acumulada (CDF) Normal Estándar
  // Aproximación numérica precisa para evitar librerías pesadas de C++
  static double normalCDF(double z) {
    if (z < -10.0) return 0.0;
    if (z > 10.0) return 1.0;

    // Constantes de aproximación de Abramowitz & Stegun
    double p = 0.2316419;
    double b1 = 0.319381530;
    double b2 = -0.356563782;
    double b3 = 1.781477937;
    double b4 = -1.821255978;
    double b5 = 1.330274429;

    double t = 1.0 / (1.0 + p * z.abs());
    double t2 = t * t;
    double t3 = t2 * t;
    double t4 = t3 * t;
    double t5 = t4 * t;

    double probability =
        1.0 -
        (1.0 / sqrt(2 * pi)) *
            exp(-0.5 * z * z) *
            (b1 * t + b2 * t2 + b3 * t3 + b4 * t4 + b5 * t5);

    return z < 0 ? 1.0 - probability : probability;
  }
}
