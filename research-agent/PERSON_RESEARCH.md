# MILY — Investigación profunda de personas

Este módulo permite investigar una persona mediante fuentes públicas, con énfasis en
desambiguación, trayectoria profesional y evidencia verificable.

## Uso

```bash
python mily_research.py --person "Investiga a NOMBRE. Especifica su profesión, organización y país si los conoces."
```

Para mejorar la desambiguación se recomienda proporcionar:
- nombre público;
- profesión o área;
- organización, proyecto o empresa asociada;
- país o contexto público;
- nombre de usuario o URL pública, si existe.

## Qué analiza

- Identidad pública y posibles homónimos.
- Cronología profesional y proyectos.
- Publicaciones, repositorios y trabajos públicos.
- Cargos y afiliaciones públicas verificables.
- Declaraciones o hechos relevantes respaldados por fuentes.
- Contradicciones entre fuentes.
- Nivel de confianza de cada hallazgo.

## Fuentes prioritarias

1. Sitio web oficial o perfil institucional.
2. Publicaciones originales y documentación primaria.
3. Repositorios y actividad pública de GitHub cuando sea relevante.
4. Organizaciones, universidades, empresas y registros públicos pertinentes.
5. Medios reputados y fuentes independientes para contraste.

## Protección de privacidad

MILY no debe buscar ni compilar datos sensibles o altamente privados, incluyendo
domicilios, teléfonos personales, ubicación en tiempo real, credenciales, documentos
de identidad, información financiera, médica o sexual.

La finalidad es producir investigación factual sobre la presencia pública de una persona,
no crear perfiles invasivos ni facilitar vigilancia, acoso, doxxing o suplantación.
