import io.legado.app.model.fileBook.ImportedFileReplacement
import org.junit.Test
import org.junit.Assert.*
import java.io.File
import java.io.InputStream
import java.io.IOException
import java.nio.file.Files

class ImportedFileReplacementTest {
    private fun inDirectory(test: (File) -> Unit) {
        val dir = Files.createTempDirectory("reader-import-test").toFile()
        try { test(dir) } finally { dir.deleteRecursively() }
    }
    @Test fun sameNameOlderTimestampAndShorterFileReplacesAllOldBytes() = inDirectory { dir ->
        val old = File(dir, "book.epub").apply { writeText("old content with long trailing bytes") }
        val incoming = File(dir, "download.epub").apply { writeText("new"); setLastModified(0) }
        incoming.inputStream().use { ImportedFileReplacement.copy(it, dir) { old.outputStream() } }
        assertEquals("new", old.readText())
        assertEquals(setOf("book.epub", "download.epub"), dir.list()!!.toSet())
    }
    @Test fun sameFileImportDoesNotTruncateItsOwnInput() = inDirectory { dir ->
        val book = File(dir, "book.epub").apply { writeText("current book") }
        book.inputStream().use { ImportedFileReplacement.copy(it, dir) { book.outputStream() } }
        assertEquals("current book", book.readText())
    }
    @Test fun readFailureLeavesOriginalUntouched() = inDirectory { dir ->
        val book = File(dir, "book.epub").apply { writeText("original") }
        val input = object : InputStream() { override fun read(): Int = throw IOException("read failed") }
        try { ImportedFileReplacement.copy(input, dir) { book.outputStream() }; fail() } catch (_: IOException) { }
        assertEquals("original", book.readText())
        assertEquals(listOf("book.epub"), dir.list()!!.toList())
    }
    @Test fun emptyDownloadDoesNotReplaceBook() = inDirectory { dir ->
        val book = File(dir, "book.epub").apply { writeText("original") }
        try { ImportedFileReplacement.copy(byteArrayOf().inputStream(), dir) { book.outputStream() }; fail() }
        catch (_: IllegalArgumentException) { }
        assertEquals("original", book.readText())
    }
}
