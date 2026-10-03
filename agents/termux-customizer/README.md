# MILY Termux Customizer Agent

Agente para personalizar Termux de forma segura y reversible.

## Funciones
- Configurar prompt y bienvenida.
- Crear aliases útiles.
- Personalizar colores y apariencia mediante archivos de configuración.
- Configurar shell Bash.
- Crear respaldos antes de modificar archivos.
- Restaurar la configuración anterior.
- Mostrar un resumen de los cambios.
- Detectar paquetes disponibles antes de instalar herramientas.
- Mantener la personalización separada del núcleo de MILY.

## Comandos previstos
- `customize` — aplicar una configuración.
- `preview` — mostrar cambios sin aplicarlos.
- `backup` — crear respaldo.
- `restore` — restaurar respaldo.
- `reset` — volver a una configuración básica.
- `status` — revisar configuración actual.

## Seguridad
El agente no modifica archivos del sistema Android ni intenta obtener permisos elevados. Antes de modificar archivos de Termux debe crear un respaldo y permitir restaurarlo.
