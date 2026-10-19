// Microfono «pulito» per Aria: lo stesso filtro eco e riduzione rumore che usano le chiamate FaceTime (Voice Processing di macOS).
// Aria parla dalle casse del Mac e il microfono le risente: con questo filtro la voce di Aria viene tolta dal microfono (misurato: 20-30 dB, contro i 6-9 del filtro
// fatto in casa) e resta solo l'utente, quindi si puo' interromperla a voce anche mentre parla senza pause.
//
// Uso: aria-vpmic            (nessun argomento)
// Su stdout: una riga «READY <frequenza>» e poi per sempre blocchi da 512 campioni, mono, int16 little-endian, a 16 kHz.
// Esce da solo se il programma che l'ha lanciato chiude stdin (cioe' se Aria si chiude) o se il dispositivo audio cambia (AirPods collegati/scollegati: Aria lo rilancia).
import AVFoundation
import Foundation

setvbuf(stdout, nil, _IOFBF, 0)
func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data((msg + "\n").utf8))
    exit(1)
}

let engine = AVAudioEngine()
let input = engine.inputNode
do { try input.setVoiceProcessingEnabled(true) } catch { fail("voice processing non disponibile: \(error)") }
if #available(macOS 14.0, *) {
    // la musica o un video che stanno andando non vanno abbassati solo perche' Aria ascolta
    input.voiceProcessingOtherAudioDuckingConfiguration = AVAudioVoiceProcessingOtherAudioDuckingConfiguration(enableAdvancedDucking: false, duckingLevel: .min)
}

let inFmt = input.outputFormat(forBus: 0)
guard inFmt.sampleRate > 0, inFmt.channelCount > 0 else { fail("nessun microfono") }
guard let monoFmt = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: inFmt.sampleRate, channels: 1, interleaved: false),
      let outFmt = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true),
      let conv = AVAudioConverter(from: monoFmt, to: outFmt) else { fail("conversione audio non disponibile") }

let block = 512
var pending = [Int16]()
var taps = 0                                                  // quanti blocchi del microfono sono arrivati (se restano 0 il dispositivo non manda niente)
let out = FileHandle.standardOutput
let lock = NSLock()

func quit(_ code: Int32) -> Never {
    engine.stop()
    _exit(code)                                              // _exit: exit() farebbe partire i distruttori mentre il thread audio usa ancora le variabili globali (un crash di memoria all'uscita)
}

input.installTap(onBus: 0, bufferSize: 1024, format: inFmt) { buf, _ in
    lock.lock(); taps += 1; lock.unlock()
    guard let ch = buf.floatChannelData, buf.frameLength > 0 else { return }
    guard let mono = AVAudioPCMBuffer(pcmFormat: monoFmt, frameCapacity: buf.frameLength) else { return }
    mono.frameLength = buf.frameLength
    memcpy(mono.floatChannelData![0], ch[0], Int(buf.frameLength) * MemoryLayout<Float>.size)      // il primo canale e' la voce ripulita (gli altri sono copie)
    let cap = AVAudioFrameCount(Double(buf.frameLength) * 16000.0 / inFmt.sampleRate) + 32
    guard let res = AVAudioPCMBuffer(pcmFormat: outFmt, frameCapacity: cap) else { return }
    var fed = false
    var err: NSError?
    conv.convert(to: res, error: &err) { _, status in
        if fed { status.pointee = .noDataNow; return nil }
        fed = true
        status.pointee = .haveData
        return mono
    }
    guard err == nil, res.frameLength > 0, let p = res.int16ChannelData else { return }
    lock.lock()
    pending.append(contentsOf: UnsafeBufferPointer(start: p[0], count: Int(res.frameLength)))
    while pending.count >= block {
        let chunk = Array(pending[0..<block])
        pending.removeFirst(block)
        chunk.withUnsafeBufferPointer { out.write(Data(buffer: $0)) }
    }
    lock.unlock()
}

engine.prepare()
do { try engine.start() } catch { fail("microfono non avviato: \(error)") }
out.write(Data("READY 16000\n".utf8))

// il dispositivo e' cambiato (AirPods, altro microfono): meglio ripartire da zero, ci pensa Aria
NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil) { _ in
    FileHandle.standardError.write(Data("configurazione audio cambiata\n".utf8))
    quit(2)
}
// il microfono dice «pronto» ma non manda nessun blocco (dispositivo bloccato): meglio uscire subito, Aria passa al microfono normale
Thread.detachNewThread {
    Thread.sleep(forTimeInterval: 5.0)
    lock.lock(); let n = taps; lock.unlock()
    if n == 0 {
        FileHandle.standardError.write(Data("nessun audio dal microfono\n".utf8))
        quit(3)
    }
}
// se Aria si chiude, stdin si chiude: usciamo
Thread.detachNewThread {
    while true {
        let d = FileHandle.standardInput.availableData
        if d.isEmpty { quit(0) }
    }
}
RunLoop.main.run()
