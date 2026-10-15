#!/usr/bin/env python3
import pathlib, sys
if len(sys.argv) != 2: raise SystemExit("usage: patch_android_backend_auth.py PROJECT_ROOT")
root=pathlib.Path(sys.argv[1]).resolve()
def rd(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s):
 q=root/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s,encoding="utf-8")
def rep(p,a,b):
 s=rd(p); n=s.count(a)
 if n!=1: raise SystemExit(f"Patch anchor count in {p}: {n} for {a[:70]!r}")
 wr(p,s.replace(a,b,1))
main="app/src/main/java/com/example/MainActivity.kt"
settings="app/src/main/java/com/example/data/ai/MilyBackendSettings.kt"
provider="app/src/main/java/com/example/data/ai/OpenAiBackendProvider.kt"
realtime="app/src/main/java/com/example/data/ai/MilyRealtimeClient.kt"
repo="app/src/main/java/com/example/data/repository/ChatRepository.kt"
vm="app/src/main/java/com/example/ui/viewmodel/ChatViewModel.kt"
screen="app/src/main/java/com/example/ui/screens/ChatScreen.kt"
ui="app/src/main/java/com/example/ui/components/SettingsDialog.kt"
tests="app/src/test/java/com/example/data/ai/MilyBackendSettingsTest.kt"
if not (root/main).is_file(): raise SystemExit("Not a MILY Android project")
if (root/settings).exists():
 if 'Bearer $token' in rd(provider) and 'Bearer $token' in rd(realtime) and 'mily_backend_token_input' in rd(ui):
  print("MILY backend auth patch already applied"); raise SystemExit(0)
 raise SystemExit("Partial backend-auth patch; refusing to continue")
wr(settings, r'''package com.example.data.ai
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.example.BuildConfig
import java.net.URI
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Per-device backend configuration; the client token is encrypted with Android Keystore. */
class MilyBackendSettings(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("mily_connection_settings", Context.MODE_PRIVATE)
    fun baseUrl(): String = prefs.getString("backend_base_url", null) ?: (normalizeBaseUrl(BuildConfig.MILY_BACKEND_URL.trim()) ?: "")
    fun saveBaseUrl(value: String) { prefs.edit().putString("backend_base_url", value.trim()).apply() }
    fun apiToken(): String {
        val value = prefs.getString("backend_token", null) ?: return ""
        return runCatching { decrypt(value) }.getOrElse { prefs.edit().remove("backend_token").apply(); "" }
    }
    fun saveApiToken(value: String) {
        if (value.isBlank()) prefs.edit().remove("backend_token").apply()
        else prefs.edit().putString("backend_token", encrypt(value.trim())).apply()
    }
    private fun encrypt(value: String): String {
        val c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE,key())
        val body=c.doFinal(value.toByteArray(Charsets.UTF_8)); val iv=c.iv
        val packed=ByteArray(1+iv.size+body.size); packed[0]=iv.size.toByte()
        System.arraycopy(iv,0,packed,1,iv.size); System.arraycopy(body,0,packed,1+iv.size,body.size)
        return Base64.encodeToString(packed,Base64.NO_WRAP)
    }
    private fun decrypt(value: String): String {
        val p=Base64.decode(value,Base64.NO_WRAP); require(p.isNotEmpty())
        val n=p[0].toInt() and 255; require(n in 12..16 && p.size>1+n)
        val c=Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,p.copyOfRange(1,1+n)))
        return String(c.doFinal(p.copyOfRange(1+n,p.size)),Charsets.UTF_8)
    }
    private fun key(): SecretKey {
        val ks=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey("mily.client.token.v1",null) as? SecretKey)?.let { return it }
        val gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder("mily.client.token.v1",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true).build())
        return gen.generateKey()
    }
    companion object {
        fun normalizeBaseUrl(raw: String): String? {
            val v=raw.trim(); if (v.isBlank() || v.any { it.isWhitespace() }) return null
            val u=runCatching { URI(v) }.getOrNull() ?: return null
            if (!u.scheme.equals("https",true) || u.host.isNullOrBlank() || u.rawUserInfo!=null || u.rawQuery!=null || u.rawFragment!=null) return null
            return v.trimEnd('/')+"/"
        }
    }
}
''')
wr(provider, r'''package com.example.data.ai
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

/** OpenAI API credentials stay on the backend; Android sends only the configured client token. */
class OpenAiBackendProvider(private val backendSettings: MilyBackendSettings) : AiProvider {
    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder().connectTimeout(20,TimeUnit.SECONDS).readTimeout(90,TimeUnit.SECONDS).writeTimeout(30,TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val token=backendSettings.apiToken(); val req=chain.request().newBuilder()
                if (token.isNotBlank()) req.header("Authorization","Bearer $token")
                chain.proceed(req.build())
            }.build()
    }
    private fun service(): OpenAiBackendService? {
        val url=MilyBackendSettings.normalizeBaseUrl(backendSettings.baseUrl()) ?: return null
        return Retrofit.Builder().baseUrl(url).client(client).addConverterFactory(MoshiConverterFactory.create())
            .build().create(OpenAiBackendService::class.java)
    }
    override suspend fun generate(request: AiRequest): Result<AiResponse> {
        val api=service() ?: return Result.failure(IllegalStateException("Configura una URL HTTPS válida del backend de MILY en Ajustes."))
        return runCatching {
            val r=api.generate(OpenAiBackendRequest(
                model=request.model, instructions=request.systemPrompt,
                input=request.history.map { OpenAiInputMessage(it.role,it.content) },
                temperature=request.temperature, maxOutputTokens=request.maxOutputTokens,
                memoryFacts=request.memoryFacts, enableFileSearch=request.enableFileSearch,
                maxFileSearchResults=request.maxFileSearchResults))
            val text=r.text ?: r.outputText ?: r.error ?: "El backend de Mily no devolvió texto."
            if (!r.error.isNullOrBlank()) error(r.error)
            AiResponse(text=text, tokenCount=r.tokenCount ?: text.split(" ").size)
        }
    }
}
''')
rep(realtime,"    private val backendUrl: String,\n    private val config: OpenAiRealtimeConfig = OpenAiRealtimeConfig()",
    "    private val backendSettings: MilyBackendSettings,\n    private val config: OpenAiRealtimeConfig = OpenAiRealtimeConfig()")
rep(realtime,"        if (state == State.CONNECTING || state == State.CONNECTED) return\n        state = State.CONNECTING",
    "        if (state == State.CONNECTING || state == State.CONNECTED) return\n        if (MilyBackendSettings.normalizeBaseUrl(backendSettings.baseUrl()) == null) { fail(\"Configura una URL HTTPS válida del backend de MILY en Ajustes.\", onState); return }\n        state = State.CONNECTING")
rep(realtime,'''                val base = backendUrl.trimEnd('/')
                val request = Request.Builder()
                    .url("$base/v1/mily/live/sessions")
                    .post(body.toRequestBody("application/json".toMediaType()))
                    .build()''',
'''                val base = MilyBackendSettings.normalizeBaseUrl(backendSettings.baseUrl())?.trimEnd('/')
                    ?: error("Configura una URL HTTPS válida del backend de MILY en Ajustes.")
                val builder = Request.Builder().url("$base/v1/mily/live/sessions")
                    .post(body.toRequestBody("application/json".toMediaType()))
                val token = backendSettings.apiToken()
                if (token.isNotBlank()) builder.header("Authorization", "Bearer $token")
                val request = builder.build()''')
rep(main,"import com.example.data.ai.MilyRealtimeClient\n","import com.example.data.ai.MilyRealtimeClient\nimport com.example.data.ai.MilyBackendSettings\n")
rep(main,"MilyRealtimeClient(this, BuildConfig.MILY_BACKEND_URL)","MilyRealtimeClient(this, MilyBackendSettings(applicationContext))")
rep(repo,"import com.example.data.ai.AiRequest\nimport com.example.data.ai.OpenAiBackendProvider\n","import com.example.data.ai.AiRequest\nimport com.example.data.ai.MilyBackendSettings\nimport com.example.data.ai.OpenAiBackendProvider\n")
rep(repo,"    private val chatDao: ChatDao,\n    val memoryDao: MemoryDao,\n    val episodicDao: EpisodicMemoryDao? = null,","    private val chatDao: ChatDao,\n    val memoryDao: MemoryDao,\n    private val backendSettings: MilyBackendSettings,\n    val episodicDao: EpisodicMemoryDao? = null,")
rep(repo,"private val openAiProvider = OpenAiBackendProvider()","private val openAiProvider = OpenAiBackendProvider(backendSettings)")
rep(vm,"import com.example.data.local.AppDatabase\n","import com.example.data.ai.MilyBackendSettings\nimport com.example.data.local.AppDatabase\n")
rep(vm,"class ChatViewModel(application: Application) : AndroidViewModel(application) {\n    private val database = AppDatabase.getInstance(application)","class ChatViewModel(application: Application) : AndroidViewModel(application) {\n    private val backendSettings = MilyBackendSettings(application)\n    private val database = AppDatabase.getInstance(application)")
rep(vm,"        database.chatDao(),\n        database.memoryDao(),\n        database.episodicMemoryDao(),","        database.chatDao(),\n        database.memoryDao(),\n        backendSettings,\n        database.episodicMemoryDao(),")
rep(vm,"    val customApiKey: String = \"\",\n    val temperature: Float = 0.7f,","    val customApiKey: String = \"\",\n    val backendUrl: String = \"\",\n    val backendToken: String = \"\",\n    val temperature: Float = 0.7f,")
rep(vm,"    private val _uiState = MutableStateFlow(ChatUiState())","    private val _uiState = MutableStateFlow(ChatUiState(backendUrl = backendSettings.baseUrl(), backendToken = backendSettings.apiToken()))")
rep(vm,"""    fun updateApiKey(key: String) {
        _uiState.value = _uiState.value.copy(customApiKey = key)
    }

    fun updateTemperature(temp: Float) {""",
"""    fun updateApiKey(key: String) {
        _uiState.value = _uiState.value.copy(customApiKey = key)
    }
    fun updateBackendUrl(url: String) {
        backendSettings.saveBaseUrl(url); _uiState.value = _uiState.value.copy(backendUrl = url)
    }
    fun updateBackendToken(token: String) {
        runCatching { backendSettings.saveApiToken(token) }
            .onSuccess { _uiState.value = _uiState.value.copy(backendToken = token, errorMessage = null) }
            .onFailure { _uiState.value = _uiState.value.copy(errorMessage = "No se pudo guardar el token de forma segura.") }
    }
    fun updateTemperature(temp: Float) {""")
rep(screen,"""            apiKey = uiState.customApiKey,
            onApiKeyChange = { viewModel.updateApiKey(it) },
            temperature = uiState.temperature,""",
"""            apiKey = uiState.customApiKey,
            onApiKeyChange = { viewModel.updateApiKey(it) },
            backendUrl = uiState.backendUrl,
            onBackendUrlChange = { viewModel.updateBackendUrl(it) },
            backendToken = uiState.backendToken,
            onBackendTokenChange = { viewModel.updateBackendToken(it) },
            temperature = uiState.temperature,""")
rep(ui,"import androidx.compose.ui.text.font.FontWeight\n","import androidx.compose.ui.text.font.FontWeight\nimport androidx.compose.ui.text.input.PasswordVisualTransformation\n")
rep(ui,"    apiKey: String,\n    onApiKeyChange: (String) -> Unit,\n    temperature: Float,","    apiKey: String,\n    onApiKeyChange: (String) -> Unit,\n    backendUrl: String,\n    onBackendUrlChange: (String) -> Unit,\n    backendToken: String,\n    onBackendTokenChange: (String) -> Unit,\n    temperature: Float,")
rep(ui,"    var showConfirmDelete by remember { mutableStateOf(false) }\n    var tempKey by remember { mutableStateOf(apiKey) }\n    var tempVal by remember { mutableFloatStateOf(temperature) }","    var showConfirmDelete by remember { mutableStateOf(false) }\n    var tempKey by remember { mutableStateOf(apiKey) }\n    var tempBackendUrl by remember { mutableStateOf(backendUrl) }\n    var tempBackendToken by remember { mutableStateOf(backendToken) }\n    var tempVal by remember { mutableFloatStateOf(temperature) }")
rep(ui,"""            Spacer(modifier = Modifier.height(20.dp))

            // 3. Creativity / Temperature""",
"""            Spacer(modifier = Modifier.height(20.dp))
            Text("Conexión con el servidor de MILY", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("Configura la URL HTTPS y el token de cliente del hosting. No introduzcas aquí la clave del proveedor de IA.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(value=tempBackendUrl, onValueChange={ tempBackendUrl=it; onBackendUrlChange(it) },
                modifier=Modifier.fillMaxWidth().testTag("mily_backend_url_input"), label={ Text("URL base HTTPS") },
                placeholder={ Text("https://tu-servidor.example") }, singleLine=true,
                leadingIcon={ Icon(imageVector=Icons.Default.WifiTethering, contentDescription=null) }, shape=RoundedCornerShape(12.dp))
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(value=tempBackendToken, onValueChange={ tempBackendToken=it; onBackendTokenChange(it) },
                modifier=Modifier.fillMaxWidth().testTag("mily_backend_token_input"), label={ Text("Token de cliente") },
                placeholder={ Text("Token configurado en el hosting") }, singleLine=true,
                visualTransformation=PasswordVisualTransformation(),
                leadingIcon={ Icon(imageVector=Icons.Default.Key, contentDescription=null) }, shape=RoundedCornerShape(12.dp))
            Text("El token se cifra con Android Keystore y las peticiones solo se envían por HTTPS.",
                style=MaterialTheme.typography.bodySmall, color=MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(modifier = Modifier.height(20.dp))

            // 3. Creativity / Temperature""")
wr(tests, r'''package com.example.data.ai
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
class MilyBackendSettingsTest {
 @Test fun acceptsHttpsAndAddsSlash() {
  assertEquals("https://api.example.com/", MilyBackendSettings.normalizeBaseUrl("https://api.example.com"))
 }
 @Test fun rejectsHttpAndUnsafeUrls() {
  listOf("http://api.example.com","not-a-url","https://user:pass@api.example.com","https://api.example.com/?token=x","https://api.example.com/#x")
   .forEach { assertNull(MilyBackendSettings.normalizeBaseUrl(it)) }
 }
}
''')
checks = [
    'Bearer $token' in rd(provider), 'Bearer $token' in rd(realtime),
    'mily_backend_token_input' in rd(ui), 'backendUrl = backendSettings.baseUrl()' in rd(vm),
    'OpenAiBackendProvider(backendSettings)' in rd(repo),
    'MilyRealtimeClient(this, MilyBackendSettings(applicationContext))' in rd(main),
]
if not all(checks): raise SystemExit("Post-patch validation failed")
print("MILY Android HTTPS and Bearer-auth patch applied.")
