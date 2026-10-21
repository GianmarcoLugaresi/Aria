import Foundation

/// Un testo lungo diviso in righe corte per il menu nella barra in alto: una voce di menu non va a capo da sola, quindi una riga lunga (come «Primo avvio: sto scaricando
/// i modelli…») allargherebbe tutto il pannello. Si spezza tra le parole; una parola piu' lunga del limite resta intera.
func wrapMenuText(_ text: String, width: Int = 40) -> [String] {
    var lines: [String] = []
    var current = ""
    for word in text.split(separator: " ") {
        if !current.isEmpty && current.count + 1 + word.count > width {
            lines.append(current)
            current = String(word)
        } else {
            current += (current.isEmpty ? "" : " ") + word
        }
    }
    if !current.isEmpty { lines.append(current) }
    return lines
}
