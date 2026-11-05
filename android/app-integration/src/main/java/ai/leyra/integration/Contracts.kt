package ai.leyra.integration

/**
 * Contrato compartido entre el motor de integración de LEYRA y el dispositivo.
 *
 * El motor (Python o Kotlin) decide *qué* está permitido; esta capa solo ejecuta
 * mecanismos públicos de Android: Intents, deep links, ClipData y ContentResolver.
 * Nunca accede a datos privados de otras aplicaciones ni elude permisos.
 */
interface PlatformBridge {
    val name: String

    /** Indica si el puente puede despachar acciones ahora mismo. */
    fun available(): Boolean

    /** Consulta las aplicaciones visibles para LEYRA. */
    fun discover(): List<DiscoveredApp>

    /** Ejecuta un paso ya autorizado por el motor. */
    fun dispatch(step: ActionStep): ExecutionResult
}

data class DiscoveredApp(
    val packageName: String,
    val label: String,
    val versionName: String,
    val versionCode: Long
)

data class ActionStep(
    val connectorId: String,
    val packageName: String,
    val actionId: String,
    /** launch | share | deep_link | app_link | content_provider | shortcut */
    val actionKind: String,
    val arguments: Map<String, String> = emptyMap(),
    val requiresConfirmation: Boolean = false
)

data class ExecutionResult(
    /** ok | unavailable | denied | failed | confirmation_required | cancelled */
    val status: String,
    val detail: String,
    val data: Map<String, String> = emptyMap()
) {
    companion object {
        fun ok(detail: String, data: Map<String, String> = emptyMap()) = ExecutionResult("ok", detail, data)
        fun unavailable(detail: String) = ExecutionResult("unavailable", detail)
        fun denied(detail: String) = ExecutionResult("denied", detail)
        fun failed(detail: String) = ExecutionResult("failed", detail)
    }
}

enum class CapabilityStatus { FULL, PARTIAL, OPEN_ONLY, INCOMPATIBLE }

/** Espejo de `ConnectorManifest` del motor de LEYRA. */
data class ConnectorManifest(
    val id: String,
    val name: String,
    val packageName: String,
    val version: String,
    val level: Int,
    val auth: String,
    val permissions: List<String>,
    val actions: List<ConnectorAction>
)

data class ConnectorAction(
    val id: String,
    val label: String,
    val kind: String,
    val level: Int,
    val permissions: List<String>,
    val destructive: Boolean
)
