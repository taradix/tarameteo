package ca.taram.meteo

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.companion.AssociationRequest
import android.companion.BluetoothLeDeviceFilter
import android.companion.CompanionDeviceManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.IntentSender
import android.os.Build
import android.os.ParcelUuid
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import com.google.android.gms.maps.model.LatLng
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlin.time.Duration.Companion.seconds

// The station's side of this is firmware/lib/BleProvisioning/include/IBleProvisioner.h; BleTest checks them.
private fun uuid(n: Int) = UUID.fromString("6d5a%04x-8b6e-4b3a-9c1d-2f7a5e0c1a01".format(n))
val SERVICE: UUID = uuid(1)
val SSID: UUID = uuid(2)
val PASSWORD: UUID = uuid(3)
val LOCATION: UUID = uuid(4)
val COMMIT: UUID = uuid(5)
val STATUS: UUID = uuid(6)
val LABEL: UUID = uuid(7)
val NETWORKS: UUID = uuid(8)
val SERVER: UUID = uuid(9)
val PORT: UUID = uuid(10)
val INTERVAL: UUID = uuid(11)
// Client Characteristic Configuration: turns notifications on.
private val CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

// Room for the longest field (a 64-byte password) in one write.
private const val MTU = 517
private val CONNECT_TIMEOUT = 30.seconds
private val REQUEST_TIMEOUT = 10.seconds
// Long enough to read the sticker and type the passkey.
private val PAIRING_TIMEOUT = 60.seconds
// The station tries the WiFi for up to WIFI_TIMEOUT_MS (30 s, firmware config.h) before it answers.
private val ANSWER_TIMEOUT = 60.seconds

// The link failed: out of range, or the station stopped listening.
class Lost(message: String) : IOException(message)

class PairingFailed : IOException("Pairing failed")

// The station said no; code is what follows "error:" (ssid, password, location, label, server, port,
// interval, wifi, storage).
class Rejected(val code: String) : IOException("Rejected: $code")

// A network for the station to join.
data class WiFiCredentials(val ssid: String, val password: String)

// Where the station sends its readings.
data class MqttServer(val host: String, val port: Int)

// The station's bounds, like CertificateManager's: a port, and seconds between readings.
val PORTS = 1..65535
val INTERVALS = 60..86400

// Two little-endian float32: latitude, then longitude.
fun location(at: LatLng): ByteArray =
    ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putFloat(at.latitude.toFloat()).putFloat(at.longitude.toFloat()).array()

// A little-endian uint16, for Port.
fun uint16(value: Int): ByteArray = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(value.toShort()).array()

// A little-endian uint32, for Interval.
fun uint32(value: Int): ByteArray = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()

// The Server and Port values.
fun mqttServerOf(host: ByteArray, port: ByteArray): MqttServer =
    MqttServer(host.decodeToString(), ByteBuffer.wrap(port).order(ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xffff)

// The Interval value: seconds between readings.
fun intervalOf(value: ByteArray): Int = ByteBuffer.wrap(value).order(ByteOrder.LITTLE_ENDIAN).int

// A WiFi network the station found, with its signal there in dBm.
data class Network(val ssid: String, val rssi: Int)

// A Networks value: entries of [int8 RSSI][uint8 length][SSID bytes], strongest first. A cut entry,
// which the station never sends, ends the list.
fun networksOf(value: ByteArray): List<Network> = buildList {
    var at = 0
    while (at + 2 <= value.size) {
        val rssi = value[at].toInt()
        val length = value[at + 1].toInt() and 0xff
        val end = at + 2 + length
        if (end > value.size) break
        add(Network(value.decodeToString(at + 2, end), rssi))
        at = end
    }
}

// The station's verdict in a Status value, or null for "idle" and "provisioning", which aren't one yet.
fun verdict(status: String): Result<Unit>? = when {
    status == "ok" -> Result.success(Unit)
    status.startsWith("error:") -> Result.failure(Rejected(status.removePrefix("error:")))
    else -> null
}

/**
 * Opens Android's device chooser, listing only stations. The app needs no scan permission for it, and
 * no location permission before Android 12. [onChooser] gets the chooser to launch, whose result goes
 * to [chosen]; [onFailure] means no station answered.
 */
fun chooseStation(context: Context, onChooser: (IntentSender) -> Unit, onFailure: () -> Unit) {
    val manager = context.getSystemService(CompanionDeviceManager::class.java)
    val filter = BluetoothLeDeviceFilter.Builder()
        .setScanFilter(ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE)).build())
        .build()
    val request = AssociationRequest.Builder().addDeviceFilter(filter).setSingleDevice(false).build()
    val callback = object : CompanionDeviceManager.Callback() {
        // NOTE: deprecated in API 33 for onAssociationPending, which calls it; override that once minSdk is 33.
        @Deprecated("Replaced by onAssociationPending in API 33")
        override fun onDeviceFound(chooser: IntentSender) = onChooser(chooser)
        override fun onFailure(error: CharSequence?) = onFailure()
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        manager.associate(request, context.mainExecutor, callback)
    } else {
        @Suppress("DEPRECATION")
        manager.associate(request, callback, null)
    }
}

// The station picked in the chooser; its advertised name is its sensor ID.
// NOTE: EXTRA_DEVICE is deprecated in API 33 for EXTRA_ASSOCIATION, whose device needs API 34; the
// chooser still fills both.
@Suppress("DEPRECATION")
fun chosen(result: Intent?): ScanResult? =
    result?.let { IntentCompat.getParcelableExtra(it, CompanionDeviceManager.EXTRA_DEVICE, ScanResult::class.java) }

// The chooser leaves an association behind, which the app has no use for once it has the device.
fun forget(context: Context, address: String) {
    val manager = context.getSystemService(CompanionDeviceManager::class.java)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        manager.myAssociations.filter { it.deviceMacAddress?.toString().equals(address, ignoreCase = true) }
            .forEach { manager.disassociate(it.id) }
    } else {
        @Suppress("DEPRECATION")
        manager.disassociate(address)
    }
}

/**
 * A connection to a station in its provisioning window. One call at a time: Android runs one GATT
 * request at a time, and every call here waits for its answer.
 */
@SuppressLint("MissingPermission") // The screen gets BLUETOOTH_CONNECT before it opens a Station.
class Station private constructor(private val gatt: BluetoothGatt, private val events: Events) : AutoCloseable {
    companion object {
        // Connects and pairs; Android asks for the passkey on the sticker the first time.
        suspend fun open(context: Context, device: BluetoothDevice): Station {
            val events = Events()
            val gatt = device.connectGatt(context, false, events, BluetoothDevice.TRANSPORT_LE)
                ?: throw Lost("Bluetooth is off")
            val station = Station(gatt, events)
            try {
                withTimeoutOrNull(CONNECT_TIMEOUT) { events.connected.await() } ?: throw Lost("No connection")
                station.request { it.discoverServices() }
                pair(context, device)
                station.request { it.requestMtu(MTU) }
                station.notifyStatus()
            } catch (e: Throwable) {
                // Leaving the screen cancels this mid-way; the station stops advertising while connected.
                station.close()
                throw e
            }
            return station
        }

        // NOTE: a phone paired before the station's identity was re-flashed holds stale keys, and every
        // read then fails; forgetting the station in the phone's Bluetooth settings fixes it.
        private suspend fun pair(context: Context, device: BluetoothDevice) {
            if (device.bondState == BluetoothDevice.BOND_BONDED) return
            val states = Channel<Int>(Channel.UNLIMITED)
            val receiver = object : BroadcastReceiver() {
                override fun onReceive(context: Context, intent: Intent) {
                    val from = IntentCompat.getParcelableExtra(intent, BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    if (from?.address == device.address) {
                        states.trySend(intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE))
                    }
                }
            }
            val filter = IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED)
            ContextCompat.registerReceiver(context, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
            try {
                if (!device.createBond()) throw PairingFailed()
                // BOND_NONE after BOND_BONDING: a wrong passkey, or the dialog dismissed.
                val paired = withTimeoutOrNull(PAIRING_TIMEOUT) {
                    var state = states.receive()
                    while (state == BluetoothDevice.BOND_BONDING) state = states.receive()
                    state == BluetoothDevice.BOND_BONDED
                }
                if (paired != true) throw PairingFailed()
            } finally {
                context.unregisterReceiver(receiver)
            }
        }
    }

    // The name the station has now, to prefill; empty for none.
    suspend fun label(): String = read(LABEL).decodeToString()

    // The networks the station found when it powered on, to pick from.
    suspend fun networks(): List<Network> = networksOf(read(NETWORKS))

    // Where the station sends its readings now, and how often, to prefill.
    suspend fun mqttServer(): MqttServer = mqttServerOf(read(SERVER), read(PORT))
    suspend fun interval(): Int = intervalOf(read(INTERVAL))

    // Sends the settings and waits for the station's verdict, which throws Rejected when it says no. A null
    // server or interval isn't sent, so the station keeps its own.
    suspend fun provision(wifi: WiFiCredentials, at: LatLng, label: String, server: MqttServer?, interval: Int?) {
        write(SSID, wifi.ssid.encodeToByteArray())
        write(PASSWORD, wifi.password.encodeToByteArray())
        write(LOCATION, location(at))
        write(LABEL, label.encodeToByteArray())
        server?.let {
            write(SERVER, it.host.encodeToByteArray())
            write(PORT, uint16(it.port))
        }
        interval?.let { write(INTERVAL, uint32(it)) }
        // A verdict a timed-out commit got late isn't this one's.
        while (events.statuses.tryReceive().isSuccess) continue
        write(COMMIT, byteArrayOf(1))
        val result = withTimeoutOrNull(ANSWER_TIMEOUT) {
            var result: Result<Unit>? = null
            while (result == null) result = verdict(events.statuses.receive())
            result
        } ?: throw Lost("No answer")
        result.getOrThrow()
    }

    override fun close() {
        gatt.disconnect()
        gatt.close()
    }

    private fun characteristic(uuid: UUID) =
        gatt.getService(SERVICE)?.getCharacteristic(uuid) ?: throw Lost("Not a TaraMeteo station")

    private suspend fun notifyStatus() {
        val status = characteristic(STATUS)
        if (!gatt.setCharacteristicNotification(status, true)) throw Lost("Status notifications refused")
        val descriptor = status.getDescriptor(CCCD) ?: throw Lost("Not a TaraMeteo station")
        val on = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
        request {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                it.writeDescriptor(descriptor, on) == BluetoothStatusCodes.SUCCESS
            } else {
                @Suppress("DEPRECATION")
                descriptor.value = on
                @Suppress("DEPRECATION")
                it.writeDescriptor(descriptor)
            }
        }
    }

    private suspend fun read(uuid: UUID): ByteArray {
        val characteristic = characteristic(uuid)
        return request { it.readCharacteristic(characteristic) }
    }

    private suspend fun write(uuid: UUID, value: ByteArray) {
        val characteristic = characteristic(uuid)
        val type = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        request {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                it.writeCharacteristic(characteristic, value, type) == BluetoothStatusCodes.SUCCESS
            } else {
                characteristic.writeType = type
                @Suppress("DEPRECATION")
                characteristic.value = value
                @Suppress("DEPRECATION")
                it.writeCharacteristic(characteristic)
            }
        }
    }

    // Starts a GATT request and waits for the callback that answers it, with the value it carries.
    private suspend fun request(start: (BluetoothGatt) -> Boolean): ByteArray {
        val answer = CompletableDeferred<ByteArray>()
        events.pending = answer
        if (!start(gatt)) throw Lost("Request refused")
        return withTimeoutOrNull(REQUEST_TIMEOUT) { answer.await() } ?: throw Lost("No answer")
    }

    // Runs on a binder thread; hands each answer to the waiting request.
    private class Events : BluetoothGattCallback() {
        val connected = CompletableDeferred<Unit>()
        @Volatile var pending: CompletableDeferred<ByteArray>? = null
        val statuses = Channel<String>(Channel.UNLIMITED)

        private fun answer(status: Int, value: ByteArray = ByteArray(0)) {
            val pending = pending ?: return
            // Insufficient authentication or encryption lands here too: see the NOTE on pair().
            if (status == BluetoothGatt.GATT_SUCCESS) pending.complete(value) else pending.completeExceptionally(Lost("GATT status $status"))
        }

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connected.complete(Unit)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                val lost = Lost("Disconnected ($status)")
                connected.completeExceptionally(lost)
                pending?.completeExceptionally(lost)
                statuses.close(lost)
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) = answer(status)
        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) = answer(status)
        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) = answer(status)
        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) =
            answer(status)

        // API 33 passes the value; before that, it is on the characteristic.
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, status: Int) =
            answer(status, value)

        @Deprecated("Replaced in API 33")
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) =
            @Suppress("DEPRECATION")
            answer(status, characteristic.value)

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            statuses.trySend(value.decodeToString())
        }

        @Deprecated("Replaced in API 33")
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION")
            statuses.trySend(characteristic.value.decodeToString())
        }
    }
}
