package ai.leyra.integration

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings

/**
 * Implementación de referencia del puente Android.
 *
 * Solo despacha lo que el motor ya planificó y el usuario autorizó. Comprueba
 * resolución y permisos antes de lanzar nada y devuelve un resultado honesto.
 * No lee datos de otras apps. Para compartir archivos requiere un FileProvider
 * declarado por la app anfitriona.
 */
class AppIntegrationBridge(
    private val context: Context,
    private val discovery: PackageDiscovery = PackageDiscovery(context),
    private val fileProviderAuthority: String? = null
) : PlatformBridge {

    override val name: String = "leyra-android-bridge"

    override fun available(): Boolean = true

    override fun discover(): List<DiscoveredApp> = discovery.discover()

    override fun dispatch(step: ActionStep): ExecutionResult {
        val packageName = step.packageName.ifBlank { return ExecutionResult.denied("Falta el paquete de destino.") }
        if (!isInstalled(packageName)) {
            return ExecutionResult.unavailable("La aplicación no está instalada o no es visible para LEYRA.")
        }
        return try {
            when (step.actionKind) {
                "launch" -> launch(packageName)
                "share" -> share(step)
                "deep_link", "app_link" -> openLink(step)
                "content_provider" -> readPublicProvider(step)
                "shortcut" -> reportShortcut(packageName)
                else -> ExecutionResult.failed("Acción no soportada por el puente: ${step.actionKind}")
            }
        } catch (error: ActivityNotFoundException) {
            ExecutionResult.failed("La aplicación no tiene una actividad pública para esta acción.")
        } catch (error: SecurityException) {
            ExecutionResult.denied("Android denegó la operación: la app destino no exporta esa interfaz.")
        } catch (error: IllegalArgumentException) {
            ExecutionResult.failed("Parámetros no válidos para la acción solicitada.")
        }
    }

    private fun isInstalled(packageName: String): Boolean = runCatching {
        context.packageManager.getPackageInfo(packageName, 0)
        true
    }.getOrDefault(false)

    private fun start(intent: Intent, packageName: String): ExecutionResult {
        intent.setPackage(packageName)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.resolveActivity(context.packageManager) == null) {
            return ExecutionResult.unavailable("La app no declara un intent público que acepte esta acción.")
        }
        context.startActivity(intent)
        return ExecutionResult.ok("Intent enviado a $packageName", mapOf("action" to intent.action.orEmpty()))
    }

    private fun launch(packageName: String): ExecutionResult {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_LAUNCHER)
                .setPackage(packageName)
        return start(intent, packageName)
    }

    private fun share(step: ActionStep): ExecutionResult {
        val text = step.arguments["text"] ?: step.arguments["content"] ?: step.arguments["message"]
        val uri = step.arguments["file"] ?: step.arguments["uri"]
        val intent = Intent(Intent.ACTION_SEND)
        if (!uri.isNullOrBlank()) {
            if (fileProviderAuthority.isNullOrBlank()) {
                return ExecutionResult.failed("Compartir archivos requiere un FileProvider configurado en LEYRA.")
            }
            val contentUri: Uri = runCatching { Uri.parse(uri) }
                .getOrElse { return ExecutionResult.failed("URI de archivo inválida.") }
            intent.type = step.arguments["mimeType"] ?: context.contentResolver.getType(contentUri) ?: "*/*"
            intent.putExtra(Intent.EXTRA_STREAM, contentUri)
            intent.clipData = ClipData.newRawUri("LEYRA", contentUri)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } else if (!text.isNullOrBlank()) {
            intent.type = "text/plain"
            intent.putExtra(Intent.EXTRA_TEXT, text)
            intent.clipData = ClipData.newPlainText("LEYRA", text)
        } else {
            return ExecutionResult.failed("La acción de compartir no recibió texto ni archivo.")
        }
        return start(intent, step.packageName)
    }

    private fun openLink(step: ActionStep): ExecutionResult {
        val url = step.arguments["url"] ?: step.arguments["link"]
            ?: return ExecutionResult.failed("Falta el enlace a abrir.")
        val parsed = Uri.parse(url)
        if (parsed.scheme?.lowercase() !in setOf("http", "https")) {
            return ExecutionResult.denied("Solo se permiten enlaces http(s).")
        }
        return start(Intent(Intent.ACTION_VIEW, parsed), step.packageName)
    }

    /**
     * Lectura de un `ContentProvider` público con URIs `content://` concedidas por el
     * usuario. Si la app no exporta el proveedor, Android lanza SecurityException y se
     * informa como denegado: no se intenta ningún rodeo.
     */
    private fun readPublicProvider(step: ActionStep): ExecutionResult {
        val raw = step.arguments["uri"] ?: return ExecutionResult.failed("Falta el URI del proveedor.")
        val uri = Uri.parse(raw)
        if (uri.scheme != "content") {
            return ExecutionResult.denied("Solo se admiten URIs content://.")
        }
        val columns = step.arguments["columns"]?.split(",")?.map { it.trim() }?.toTypedArray()
        context.contentResolver.query(uri, columns, null, null, null).use { cursor ->
            if (cursor == null) return ExecutionResult.unavailable("El proveedor no devolvió datos.")
            if (cursor.moveToFirst()) {
                val values = cursor.columnNames.associateWith { name ->
                    cursor.getString(cursor.getColumnIndexOrThrow(name)) ?: ""
                }
                return ExecutionResult.ok("Consulta pública completada.", values)
            }
        }
        return ExecutionResult.ok("Consulta completada sin filas.")
    }

    /** Los atajos dinámicos se pueden listar, pero no ejecutarse desde otra app. */
    private fun reportShortcut(packageName: String): ExecutionResult {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.N_MR1) {
            return ExecutionResult.unavailable("Los atajos requieren Android 7.1 o superior.")
        }
        val manager = context.getSystemService(android.content.pm.ShortcutManager::class.java)
        val count = manager?.dynamicShortcuts?.size ?: 0
        return ExecutionResult.ok(
            "La app declara $count atajos dinámicos; Android no permite ejecutarlos desde otra aplicación.",
            mapOf("shortcuts" to count.toString(), "package" to packageName)
        )
    }

    /** Abre los ajustes de la app, útil cuando falta un permiso que solo el usuario concede. */
    fun openAppSettings(packageName: String): ExecutionResult = runCatching {
        context.startActivity(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        ExecutionResult.ok("Ajustes de $packageName abiertos.")
    }.getOrElse { ExecutionResult.failed("No se pudieron abrir los ajustes de la aplicación.") }
}
