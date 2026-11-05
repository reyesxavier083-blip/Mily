package ai.leyra.integration

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.os.Build

/**
 * Descubrimiento de aplicaciones visibles mediante `PackageManager`.
 *
 * Requiere declarar `<queries>` en el manifiesto (ver AndroidManifest.queries.xml).
 * No usa `QUERY_ALL_PACKAGES`: solo se consultan las apps que exponen lanzador.
 */
class PackageDiscovery(
    private val context: Context,
    private val maxApps: Int = 300
) {
    fun discover(): List<DiscoveredApp> {
        val manager = context.packageManager
        val launcherIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved: List<ResolveInfo> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            manager.queryIntentActivities(launcherIntent, PackageManager.ResolveInfoFlags.of(0L))
        } else {
            @Suppress("DEPRECATION")
            manager.queryIntentActivities(launcherIntent, 0)
        }

        return resolved.asSequence()
            .mapNotNull { it.activityInfo?.applicationInfo }
            .distinctBy { it.packageName }
            .filter { it.packageName != context.packageName }
            .map { info ->
                DiscoveredApp(
                    packageName = info.packageName,
                    label = runCatching { manager.getApplicationLabel(info).toString() }
                        .getOrDefault(info.packageName),
                    versionName = runCatching { manager.getPackageInfo(info.packageName, 0).versionName ?: "0" }
                        .getOrDefault("0"),
                    versionCode = versionCodeOf(info.packageName)
                )
            }
            .sortedBy { it.label.lowercase() }
            .take(maxApps)
            .toList()
    }

    /** Comprueba que una app concreta sea visible y tenga actividad de lanzamiento. */
    fun canLaunch(packageName: String): Boolean {
        val manager = context.packageManager
        return manager.getLaunchIntentForPackage(packageName) != null ||
            manager.getLeanbackLaunchIntentForPackage(packageName) != null
    }

    private fun versionCodeOf(packageName: String): Long = runCatching {
        val info = context.packageManager.getPackageInfo(packageName, 0)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            info.versionCode.toLong()
        }
    }.getOrDefault(0L)
}
