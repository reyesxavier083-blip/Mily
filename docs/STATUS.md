# Estado de MILY

Última revisión: 2026-10-14.

## Completado y validado en el repositorio

- Pruebas automáticas de Python ejecutadas por GitHub Actions.
- Validación de rutas del espacio de trabajo con casos de traversal y enlaces simbólicos.
- Máquina de estados de tareas con transiciones permitidas.
- Memoria en proceso limitada, con tipos y procedencia.
- Bus de eventos con aislamiento de fallos de suscriptores.
- Logs JSON estructurados con límites y redacción de patrones comunes de credenciales.
- Coordinador de tareas que conecta estados, eventos y observabilidad sin ejecutar herramientas ni conceder permisos.
- Gestor de permisos por lista de confianza: bloquea herramientas no registradas, rechaza discrepancias de riesgo y requiere confirmación por llamada para operaciones con efectos.
- CI de Python: compilación de fuentes y suite de pruebas.
- Interfaz web inicial adaptable en `web/`, con chat conectado al contrato HTTP del backend, indicador de conexión y ajustes de URL sin exponer claves API.
- CI ampliado para validar la sintaxis de `web/app.js`.

## Validación de MILY Web

- El cliente web estático se añadió en la rama `feat/mily-web-client` y se propuso mediante PR #11.
- GitHub Actions ejecutó correctamente la suite `MILY tests`; en `MILY quality checks`, las pruebas Python y el paso `node --check web/app.js` terminaron correctamente durante la última consulta, aunque el job aún estaba finalizando.
- La interfaz requiere un backend accesible que implemente `GET /health` y `POST /v1/mily/responses`; no se ha desplegado un backend web público ni se ha confirmado una conversación real desde navegador.
- La interfaz web no incorpora una clave API y no guarda el historial de chat entre recargas.

## Validación del archivo Android V26

Se inspeccionó el archivo integrado localmente:

- Integridad ZIP: correcta.
- XML parseados: 10.
- Fuentes Kotlin con declaración de paquete: 51.
- Archivos JavaScript del backend: pasan `node --check`.
- No se confirmó compilación Android ni generación de APK: Gradle no pudo descargar la distribución porque el entorno no resolvió `services.gradle.org`.

El proyecto Android del archivo V26 no está expandido como fuentes en este repositorio. Por tanto, el CI actual no compila esa aplicación Android.

## Pendiente antes de declarar MILY terminado

1. Revisar y completar el PR #11 después de que todas las comprobaciones finalicen.
2. Desplegar el backend Node.js del archivo V18 en un entorno controlado y configurar la URL HTTPS en web y Android.
3. Implementar autenticación de clientes, límites de frecuencia/coste y CORS antes de exponer el backend a Internet.
4. Ejecutar una compilación Android reproducible del archivo V26/V18 en un entorno con Android SDK y acceso a la distribución Gradle.
5. Corregir cualquier error real de compilación y ejecutar pruebas Android disponibles.
6. Verificar instalación y flujo básico en un dispositivo o emulador.
7. Conectar los módulos Python entre sí en el runtime real de MILY y validar sus integraciones con herramientas mediante permisos explícitos.
8. Revisar configuración de producción, claves, permisos y comportamiento sin conexión antes de una versión final.

## Criterio de finalización

MILY no debe declararse terminado ni publicarse como APK verificado hasta que el build Android, las pruebas aplicables y una comprobación de instalación hayan concluido con éxito. La interfaz web inicial y los resultados de Python no prueban por sí solos que la aplicación Android compile ni que el backend esté desplegado.
