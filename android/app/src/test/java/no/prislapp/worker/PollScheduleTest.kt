package no.prislapp.worker

import org.junit.Assert.*
import org.junit.Test

class PollScheduleTest {
    @Test fun backgroundPollStartsAtThirtySecondsAndCapsAtFiveMinutes() {
        assertEquals(30L, PollSchedule.delaySeconds(0))
        assertEquals(60L, PollSchedule.delaySeconds(1))
        assertEquals(300L, PollSchedule.delaySeconds(100))
    }
}
