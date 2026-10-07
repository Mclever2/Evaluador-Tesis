# Tarea

Analizas la sección "{seccion}" de un proyecto de tesis de pregrado con el modelo de argumentación de Toulmin. El texto ya está dividido en oraciones numeradas. Asigna a CADA oración UNA sola función, la principal, aplicando estrictamente las reglas. No calificas la calidad ni opinas.

# Funciones y reglas

**afirmacion**: postura del AUTOR DEL PROYECTO: que existe un problema, una necesidad, una carencia o una brecha; que algo es relevante o deficiente; o qué propone o aporta el estudio.
- Toda oración del autor que señala un vacío o una carencia es afirmacion, aunque se exprese como un hecho: "no existe una caracterización formal de...", "ningún estudio aborda...", "escasean los conjuntos de datos...", "la investigación sobre X es prácticamente nula".
- Las conclusiones de otros autores citadas como evidencia NO son afirmacion: son dato.

**dato**: evidencia que se ofrece como prueba: cifras, porcentajes, estadísticas, hechos verificables de la situación, y resultados o hallazgos de estudios citados.
- Un resultado de otro estudio es SIEMPRE dato, aunque use verbos como "evidencia", "demuestra" o "permite".
- La descripción de lo que hicieron o encontraron otros autores es dato, aunque incluya "sin embargo" o "aunque".

**garantia**: oración del propio autor que explica EXPLÍCITAMENTE por qué un dato concreto sostiene una afirmación concreta. Conecta ambos y suele usar expresiones como "esto respalda...", "lo cual indica que", "esto significa que", "por tanto", "en consecuencia", "este hallazgo explica por qué".
- Si solo repite o amplía la afirmación, es afirmacion.
- Si aporta un hecho o un resultado nuevo, es dato.
- Debe existir el vínculo explícito dato → afirmación; si hay que suponerlo, no es garantía.
- Una oración de transición o de síntesis sin un dato concreto al que se refiera es ninguno: "estos antecedentes proporcionan el sustento conceptual para analizar...", "estos antecedentes sirven de base para el estudio", "la combinación de estos fenómenos crea el escenario".

**respaldo**: fundamento TEÓRICO o NORMATIVO que legitima el razonamiento: una teoría, modelo, marco de referencia, ley, norma o reglamento invocado como fundamento ("según la teoría de restricciones (Goldratt, 1984)...", "la norma ISO 9001 establece...", "el reglamento reconoce...").
- Debe NOMBRAR la teoría, modelo, marco, ley, norma o principio, o su autor. Una frase general sobre la importancia de algo ("X constituye una herramienta fundamental para...") es afirmacion.
- Si lo citado es un hallazgo empírico de un estudio, es dato.

**refutacion**: el autor reconoce una objeción, excepción o condición bajo la cual SU PROPIA afirmación podría no cumplirse, o una postura contraria a ella ("podría argumentarse que...", "esto no aplica cuando...").
- En "responde_en" indica el id de la oración donde el autor responde a esa objeción; null si no la responde.
- NO es refutación: la identificación de una brecha → afirmacion.
- NO es refutación: la crítica a estudios, métodos o enfoques previos → dato si informa un hallazgo, afirmacion si es juicio del autor.
- NO es refutación: la delimitación del alcance o las limitaciones del propio estudio ("el estudio no pretende...", "se limita a...") → ninguno.
- La palabra "sin embargo", "no obstante" o "aunque" NO basta para que una oración sea refutación.

**ninguno**: rótulos, títulos, transiciones, definiciones, preguntas de investigación, descripción de la propuesta o del procedimiento, delimitaciones del alcance, y todo lo que no cumpla ninguna de las funciones anteriores.

# Oraciones de la sección (anonimizadas)

{oraciones}

Devuelve una etiqueta por CADA id, del 1 al {n}, sin omitir ninguno.
