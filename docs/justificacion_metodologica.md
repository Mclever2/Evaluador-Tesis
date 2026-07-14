# Justificación metodológica del Evaluador de Calidad Metodológica (ECM)

## Propósito y naturaleza del instrumento

El ECM es un instrumento de medición automatizado cuya única función es evaluar
la calidad metodológica de proyectos de tesis de pregrado y reportar puntajes,
evidencias textuales y métricas. No es un asistente de mentoría ni un sistema de
mejora de redacción: esa separación es deliberada, porque un instrumento que
además modificara el objeto medido comprometería la validez de la medición. El
sistema se aplicará de forma transversal a un conjunto de proyectos en una
medición única con procedimiento doble ciego, y sus resultados se contrastarán
con las calificaciones de jurados humanos, de modo que el diseño prioriza tres
propiedades: determinismo, trazabilidad y exportación completa de datos.

## Base de contenido: rúbrica con criterios operacionalizados

El contenido del instrumento proviene de dos fuentes. La rúbrica específica de
quince secciones y cien puntos operacionaliza criterios de calidad metodológica
derivados del marco de Hernández-Sampieri y Mendoza (2018), cuyas rutas
cuantitativa, cualitativa y mixta ofrecen definiciones verificables para cada
componente del proyecto (planteamiento, hipótesis, variables, diseño, muestreo,
instrumentos y análisis). Cada ítem cita el capítulo y las páginas de referencia,
lo que permite auditar el origen normativo de cada criterio. Como precedente de
instrumentos de evaluación de calidad metodológica de tesis en el contexto
peruano se toma el trabajo de Soto (2021), del que se adopta la lógica de lista
de verificación ponderada con niveles de cumplimiento. La ficha institucional
UPAO de treinta y tres ítems se incorpora como segundo perfil, en escala de cero
a tres, precisamente para producir calificaciones comparables ítem a ítem con
las fichas que llenan los jurados humanos durante la validación.

## Protocolo de calificación: rúbrica más razonamiento por pasos

Los prompts de los jueces siguen la estructura propuesta por G-Eval (Liu et al.,
2023): definición de la tarea, criterio literal de la rúbrica, escala con
definiciones operativas por nivel y pasos de evaluación breves que guían al
modelo a localizar evidencia antes de decidir. Liu et al. mostraron que este
formato con encadenamiento de pasos y formularios de puntuación incrementa la
correlación de las calificaciones automáticas con juicios humanos frente a
prompts directos de puntuación. En el ECM cada calificación exige además una
cita textual del proyecto como evidencia y una observación diagnóstica breve,
lo que hace revisable cada decisión del juez.

## Panel de jueces y agregación por mediana

En lugar de un juez único, el ECM usa un panel de tres jueces que califican en
paralelo y un agregador determinista que consolida por mediana ordinal. La
evidencia disponible sostiene esta decisión: ChatEval (Chan et al., 2024)
mostró que los equipos de múltiples agentes evaluadores con perspectivas
diferenciadas se alinean mejor con los juicios humanos que un evaluador
individual, y PoLL (Verga et al., 2024) encontró que un panel de jueces con
agregación simple supera a un juez único grande, con menor sesgo intra modelo y
menor costo. Los tres jueces del ECM comparten criterios y escala, pero reciben
roles de atención distintos (rigor metodológico, coherencia y trazabilidad,
forma académica) para inducir diversidad de perspectiva sin alterar el
instrumento. La mediana se eligió sobre el promedio por ser el estadístico
apropiado para datos ordinales y por su robustez ante un juez atípico; el
desacuerdo extremo entre jueces (rango igual a dos niveles) se marca como
discrepancia y el ítem queda señalado para revisión humana, de modo que el
panel también funciona como detector de casos difíciles.

Como precedente directo de calificación multiagente de textos académicos,
MAGIC (Jordan et al., 2025) reportó la viabilidad de sistemas de este tipo
evaluados con kappa ponderado cuadrático contra expertos, la misma métrica de
concordancia que el ECM adopta en su fase de validación.

## Mitigación de sesgos

Dos sesgos reciben tratamiento explícito. Primero, el sesgo de identidad: antes
de enviar texto a cualquier modelo, un módulo elimina nombres de autores y
asesor, DNI, correos y ORCID, y el mapeo de reversión se conserva solo en el
equipo local, con lo que la evaluación es ciega respecto de la autoría.
Segundo, el sesgo de auto-preferencia: Panickssery, Bowman y Feng (2024)
demostraron que los modelos tienden a favorecer salidas de su propia familia,
por lo que el sistema permite configurar un modelo distinto por juez y la
documentación recomienda diversificar familias en el ciclo longitudinal. De
manera complementaria, el estudio de Liang et al. (2024) sobre retroalimentación
generada por modelos de lenguaje en manuscritos científicos muestra a la vez la
utilidad y los límites de estos sistemas frente a revisores humanos, lo que
refuerza dos decisiones del ECM: reportar el grado de acuerdo del panel en cada
evaluación y mantener a los jurados humanos como criterio de validación del
instrumento, no como elemento sustituible.

## Orquestación, determinismo y trazabilidad

El flujo se implementa como un grafo explícito de LangGraph con cinco nodos
(orquestador segmentador, tres jueces en paralelo y agregador), siguiendo la
línea de trabajos que usan esta orquestación de agentes con puntos de
validación humana, como GraphMASAL (Zeng et al., 2025). El grafo fija
temperatura cero, top_p uno y semilla constante; cada resultado registra la
versión de la rúbrica, el modo de aplicación, los modelos usados, el hash de
los prompts, la marca temporal y el costo. La estabilidad no se asume: un
subcomando de test-retest ejecuta k corridas del mismo conjunto y cuantifica la
concordancia entre corridas con kappa ponderado e ICC.

## Validación psicométrica

La validez de criterio del instrumento se examina comparando sus puntajes con
los de jurados humanos sobre un conjunto dorado: kappa ponderado cuadrático a
nivel de ítem y de total (contra cada jurado y contra la mediana del panel
humano), porcentaje de acuerdo exacto y adyacente, error absoluto medio,
correlaciones de Pearson y Spearman e ICC(2,1), con intervalos de confianza
bootstrap remuestreando proyectos. La concordancia entre los propios jurados
humanos se calcula como línea base, porque el techo razonable de un instrumento
automático es el acuerdo que los humanos logran entre sí. La interpretación de
los coeficientes sigue las bandas convencionales de Landis y Koch.

## Referencias

Chan, C. M., Chen, W., Su, Y., Yu, J., Xue, W., Zhang, S., Fu, J. y Liu, Z.
(2024). ChatEval: Towards better LLM-based evaluators through multi-agent
debate. ICLR 2024.

Hernández-Sampieri, R. y Mendoza Torres, C. P. (2018). Metodología de la
investigación: las rutas cuantitativa, cualitativa y mixta. McGraw-Hill.

Jordan, M. et al. (2025). MAGIC: Multi-agent grading of academic texts.
Precedente de calificación multiagente evaluada con QWK contra expertos.

Liang, W., Zhang, Y., Cao, H. et al. (2024). Can large language models provide
useful feedback on research papers? A large-scale empirical analysis. NEJM AI,
1(8).

Liu, Y., Iter, D., Xu, Y., Wang, S., Xu, R. y Zhu, C. (2023). G-Eval: NLG
evaluation using GPT-4 with better human alignment. EMNLP 2023.

Panickssery, A., Bowman, S. R. y Feng, S. (2024). LLM evaluators recognize and
favor their own generations. NeurIPS 2024.

Soto, A. (2021). Instrumento de evaluación de la calidad metodológica de tesis
de pregrado. Instrumento base del perfil de rúbrica específica.

Verga, P., Hofstatter, S., Althammer, S. et al. (2024). Replacing judges with
juries: Evaluating LLM generations with a panel of diverse models. arXiv.

Zeng, X. et al. (2025). GraphMASAL: Graph-based multi-agent system with
LangGraph orchestration and human validation.
