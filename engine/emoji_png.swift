import AppKit
let args = CommandLine.arguments
let text = args[1], out = args[2], px = CGFloat(Double(args[3]) ?? 160)
let font = NSFont(name: "Apple Color Emoji", size: px)!
let s = NSAttributedString(string: text, attributes: [.font: font])
let size = s.size()
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(ceil(size.width)), pixelsHigh: Int(ceil(size.height)), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
s.draw(at: .zero)
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
