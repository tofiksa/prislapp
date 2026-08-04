package no.prislapp.ui.navigation

object Routes {
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val HOME = "home"
    const val CAMERA = "camera"
    const val PROCESSING = "processing/{localId}"
    const val REVIEW = "review/{receiptId}"

    fun processing(localId: Long) = "processing/$localId"
    fun review(receiptId: String) = "review/$receiptId"
}
