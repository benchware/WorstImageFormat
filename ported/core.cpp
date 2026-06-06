#include "core.hpp"

#include <cstdlib>

namespace wimf
{
    int PaethPredictor(int a, int b, int c)
    {
        int p = a + b - c;

        int pa = std::abs(p - a);
        int pb = std::abs(p - b);
        int pc = std::abs(p - c);

        if (pa <= pb && pa <= pc)
            return a;

        if (pb <= pc)
            return b;

        return c;
    }
}