import io.legado.app.help.update.NovelTrackerReleasePolicy as Policy
import org.junit.Test
import org.junit.Assert.*
class NovelTrackerReleasePolicyTest {
    @Test fun ignoresUnrelatedAndLegacyTags() {
        assertNull(Policy.version("3.26.11030156"))
        assertNull(Policy.version("reader-epubfix-3.26.100113-test.1"))
        assertNull(Policy.version("server-v9"))
    }
    @Test fun comparesInstalledDebugVersionNumerically() {
        assertFalse(Policy.isNewer("reader-epubfix-3.26.110401", "3.26.110401debug"))
        assertTrue(Policy.isNewer("reader-epubfix-3.26.110402", "3.26.110401debug"))
        assertFalse(Policy.isNewer("reader-epubfix-3.26.100113", "3.26.110401debug"))
    }
    @Test fun rejectsCommunityOrWrongAssets() {
        val root = "https://github.com/lzl86/novel-tracker/releases/download/reader-epubfix-3.26.110402/"
        assertTrue(Policy.isAllowedDownload(root + "legado-epubfix-arm64.apk"))
        assertFalse(Policy.isAllowedDownload(root + "legado-release.apk"))
        assertFalse(Policy.isAllowedDownload(root.replace("lzl86/novel-tracker", "huajideshutiao/legado") + "legado-epubfix-arm64.apk"))
    }
}
