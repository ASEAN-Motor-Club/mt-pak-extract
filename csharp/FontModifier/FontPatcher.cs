using System;
using System.IO;

class FontPatcher
{
    static void Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("Usage: FontPatcher <input.uexp> <output.uexp>");
            Console.WriteLine("  Patches NanumSquareRound_Font.uexp to add Thai Unicode range");
            return;
        }

        var data = File.ReadAllBytes(args[0]);
        Console.WriteLine($"Input: {args[0]} ({data.Length} bytes)");

        // The uexp ends with: ... C1 83 2A 9E (bulk magic)
        // SubTypeface[0] CharacterRanges has 2 ranges:
        //   CJK: U+4E00-U+9FFF (bytes: 00 4E .. FF 9F)
        //   Katakana: U+30A0-U+30FF (bytes: A0 30 .. FF 30)
        // Then FontData with import index -3 (DroidSansFallback) and scaling factor 0.5

        // We need to add a Thai range: U+0E00-U+0E7F
        // Insert it as a third CharacterRange entry

        // The CharacterRanges array structure:
        // At offset ~0x8F: 09 02 (SubTypefaces array start)
        // Then: CharacterRanges array with 2 entries (count at some offset)
        // Each range: 11-15 bytes with LowerBound/UpperBound values

        // Let me find the exact byte pattern to patch
        // Looking for: 00 4E 00 00 00 (CJK start = 0x4E00 = 19968)
        // and: FF 9F 00 00 00 (CJK end = 0x9FFF = 40959)
        
        int cjkStartOffset = FindPattern(data, new byte[] { 0x05, 0x01, 0x00, 0x4E, 0x00, 0x00, 0x00 });
        if (cjkStartOffset < 0)
        {
            Console.WriteLine("ERROR: Could not find CJK range pattern");
            return;
        }
        Console.WriteLine($"Found CJK start at offset: 0x{cjkStartOffset:X}");

        // Find the CharacterRanges array count
        // The array structure is: 09 02 [4 bytes] [count] [entries...]
        // Let me look for the array header
        int arrayHeaderOffset = cjkStartOffset - 5; // 05 00 05 01 before the range data
        Console.WriteLine($"Array context at 0x{arrayHeaderOffset:X}: {BitConverter.ToString(data, arrayHeaderOffset, 16)}");

        // The SubTypeface[0] data structure:
        // 09 02 00 00 00 00  - SubTypefaces array start
        // 05 00              - CharacterRanges array marker?
        // 05 01 00 4E 00 00 00 - CJK start
        // 05 01 FF 9F 00 00 00 - CJK end
        // 05 00              - next section marker
        // 05 01 A0 30 00 00 00 - Katakana start  
        // 05 01 FF 30 00 00 00 - Katakana end
        // 00 00 00 00        - end of CharacterRanges
        // 03 01 00 00 00 00  - section separator
        // 05 03 ...          - Typeface section with font reference

        // To add Thai, I need to add a third pair:
        // 05 00              - section marker
        // 05 01 00 0E 00 00 00 - Thai start (0x0E00 = 3584)
        // 05 01 7F 0E 00 00 00 - Thai end (0x0E7F = 3711)

        // But this shifts all subsequent data, breaking offsets in the uasset.
        // Instead, let's REPLACE one of the existing ranges with Thai.
        // Or better: replace the Katakana range with Thai since Katakana is less important.

        // Actually, the cleanest approach: REPLACE the entire Katakana range pair with Thai
        // Katakana start: A0 30 (0x30A0 = 12448)
        // Thai start: 00 0E (0x0E00 = 3584)
        // Katakana end: FF 30 (0x30FF = 12543)
        // Thai end: 7F 0E (0x0E7F = 3711)

        // Wait, let me reconsider. The values are u32 LE.
        // Katakana start 12448 = 0x000030A0 → bytes: A0 30 00 00
        // Katakana end 12543 = 0x000030FF → bytes: FF 30 00 00
        // Thai start 3584 = 0x00000E00 → bytes: 00 0E 00 00
        // Thai end 3711 = 0x00000E7F → bytes: 7F 0E 00 00

        // But in the pattern I see: 05 01 A0 30 00 00 00
        // The 05 01 is a header, then A0 30 00 00 is the value (but only 4 bytes before next 05 01)

        // Let me find the Katakana start pattern
        int katakanaOffset = FindPattern(data, new byte[] { 0x05, 0x01, 0xA0, 0x30, 0x00, 0x00, 0x00 });
        if (katakanaOffset < 0)
        {
            Console.WriteLine("ERROR: Could not find Katakana range pattern");
            return;
        }
        Console.WriteLine($"Found Katakana start at offset: 0x{katakanaOffset:X}");

        // Create a copy and modify
        var patched = new byte[data.Length];
        Array.Copy(data, patched, data.Length);

        // Replace Katakana range with Thai range
        // Katakana start: 05 01 A0 30 00 00 00 → Thai start: 05 01 00 0E 00 00 00
        patched[katakanaOffset + 2] = 0x00; // Thai start low byte
        patched[katakanaOffset + 3] = 0x0E; // Thai start high byte

        // Katakana end: 05 01 FF 30 00 00 00 → Thai end: 05 01 7F 0E 00 00 00
        int katakanaEndOffset = katakanaOffset + 7; // Next 05 01 entry
        Console.WriteLine($"Found Katakana end at offset: 0x{katakanaEndOffset:X}");
        Console.WriteLine($"Bytes: {BitConverter.ToString(data, katakanaEndOffset, 7)}");
        
        patched[katakanaEndOffset + 2] = 0x7F; // Thai end low byte
        patched[katakanaEndOffset + 3] = 0x0E; // Thai end high byte

        Console.WriteLine($"Output: {args[1]} ({patched.Length} bytes)");
        File.WriteAllBytes(args[1], patched);
        
        // Verify
        Console.WriteLine("\nVerification:");
        Console.WriteLine($"  CJK range: U+{BitConverter.ToUInt16(data, cjkStartOffset + 2):X4}-U+{BitConverter.ToUInt16(data, cjkStartOffset + 9):X4}");
        Console.WriteLine($"  Old range2: U+{BitConverter.ToUInt16(data, katakanaOffset + 2):X4}-U+{BitConverter.ToUInt16(data, katakanaEndOffset + 2):X4}");
        Console.WriteLine($"  New range2: U+{BitConverter.ToUInt16(patched, katakanaOffset + 2):X4}-U+{BitConverter.ToUInt16(patched, katakanaEndOffset + 2):X4}");
        Console.WriteLine("Done!");
    }

    static int FindPattern(byte[] data, byte[] pattern)
    {
        for (int i = 0; i <= data.Length - pattern.Length; i++)
        {
            bool match = true;
            for (int j = 0; j < pattern.Length; j++)
            {
                if (data[i + j] != pattern[j])
                {
                    match = false;
                    break;
                }
            }
            if (match) return i;
        }
        return -1;
    }
}
