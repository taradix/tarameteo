package ca.taram.meteo

import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import java.io.File

// backend/openapi.json is the contract: every field the app reads must exist there with the same nullability,
// and be optional here exactly when the API may leave it out.
// ponytail: checks names and nullability, not number vs string; add types if a mismatch ever slips through.
class ApiContractTest {
    private val schemas = Json.parseToJsonElement(File(System.getProperty("openapi")!!).readText())
        .jsonObject.getValue("components").jsonObject.getValue("schemas").jsonObject

    private fun check(descriptor: SerialDescriptor) {
        val name = descriptor.serialName.substringAfterLast('.')
        val schema = schemas[name]?.jsonObject
        assertNotNull("$name is not in the API", schema)
        val properties = schema!!.getValue("properties").jsonObject
        val required = schema["required"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
        for (i in 0 until descriptor.elementsCount) {
            val field = descriptor.getElementName(i)
            val property = properties[field] as JsonObject?
            assertNotNull("$name.$field is not in the API", property)
            val nullable = property!!["anyOf"]?.jsonArray.orEmpty().any { it.jsonObject["type"]?.jsonPrimitive?.content == "null" }
            assertEquals("$name.$field nullable", nullable, descriptor.getElementDescriptor(i).isNullable)
            assertEquals("$name.$field optional", field !in required, descriptor.isElementOptional(i))
        }
    }

    @Test
    fun modelsMatchTheApi() = listOf(
        SensorEntry.serializer(),
        SensorList.serializer(),
        WeatherReading.serializer(),
        AggregateReading.serializer(),
        Cluster.serializer(),
        ClusterList.serializer(),
    ).forEach { check(it.descriptor) }
}
