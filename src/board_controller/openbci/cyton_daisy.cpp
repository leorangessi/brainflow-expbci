#include <vector>

#include "custom_cast.h"
#include "cyton_daisy.h"
#include "serial.h"
#include "timestamp.h"

#define START_BYTE 0xA0
#define END_BYTE_STANDARD 0xC0
#define END_BYTE_ANALOG 0xC1
#define END_BYTE_MAX 0xC6
#define NUM_DAISY_PACKETS 2


int CytonDaisy::config_board (std::string conf, std::string &response)
{
    if (gain_tracker.apply_config (conf) == (int)OpenBCICommandTypes::INVALID_COMMAND)
    {
        safe_logger (spdlog::level::warn, "invalid command: {}", conf.c_str ());
        return (int)BrainFlowExitCodes::INVALID_ARGUMENTS_ERROR;
    }
    int res = OpenBCISerialBoard::config_board (conf, response);
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        gain_tracker.revert_config ();
    }
    return res;
}

void CytonDaisy::read_thread ()
{
    // 2 consecutive 33-byte Cyton packets -> one 16-ch BrainFlow row (125 Hz).
    // Firmware may send either:
    //   A) same sample_id x2 (WiFi-style / custom serial: 0,0,1,1,2,2,...)
    //   B) sequential ids (official Daisy: 0,1,2,3,...)
    // Previous even/odd-only commit pushed twice on style A (package_num 0,0,2,2),
    // which the GUI even-only tracker counted as ~127 lost samples per duplicate.
    int res;
    unsigned char b[32];
    double accel[3] = {0.};
    int analog[3] = {0};
    int analog_count = 0;
    int accel_count = 0;
    int sequence_count = 0;
    unsigned char raw_ids[NUM_DAISY_PACKETS] = {0};
    int num_rows = board_descr["default"]["num_rows"].get<int> ();
    int pkg_ch = board_descr["default"]["package_num_channel"].get<int> ();
    int ts_ch = board_descr["default"]["timestamp_channel"].get<int> ();
    double *package = new double[num_rows];
    for (int i = 0; i < num_rows; i++)
    {
        package[i] = 0.0;
    }
    double accel_scale = (double)(0.002 / (pow (2, 4)));

    while (keep_alive)
    {
        res = serial->read_from_serial_port (b, 1);
        if (res != 1)
        {
            safe_logger (spdlog::level::debug, "unable to read 1 byte");
            continue;
        }
        if (b[0] != START_BYTE)
        {
            continue;
        }

        int remaining_bytes = 32;
        int pos = 0;
        while ((remaining_bytes > 0) && (keep_alive))
        {
            res = serial->read_from_serial_port (b + pos, remaining_bytes);
            remaining_bytes -= res;
            pos += res;
        }
        if (!keep_alive)
        {
            break;
        }

        if ((b[31] < END_BYTE_STANDARD) || (b[31] > END_BYTE_MAX))
        {
            safe_logger (spdlog::level::warn, "Wrong end byte {}", b[31]);
            continue;
        }

        unsigned char sample_id = b[0];
        if (sequence_count > 0)
        {
            unsigned char first_id = raw_ids[0];
            unsigned char expect_same = first_id;
            unsigned char expect_seq = (unsigned char)((first_id + sequence_count) & 0xFF);
            if ((sample_id != expect_same) && (sample_id != expect_seq))
            {
                safe_logger (spdlog::level::debug,
                    "16ch serial resync: group_len={} first_id={} got={}", sequence_count,
                    (int)first_id, (int)sample_id);
                sequence_count = 0;
            }
        }

        if (sequence_count == 0)
        {
            for (int i = 0; i < num_rows; i++)
            {
                package[i] = 0.0;
            }
            package[pkg_ch] = (double)sample_id;
            analog_count = 0;
            accel_count = 0;
            analog[0] = analog[1] = analog[2] = 0;
            accel[0] = accel[1] = accel[2] = 0.;
        }

        int bank = sequence_count;
        raw_ids[bank] = sample_id;

        // Bank 0 -> channels 9-16, bank 1 -> channels 1-8 (same mapping as the
        // previous even-first / odd-second serial Daisy parser).
        if (bank == 0)
        {
            for (int i = 0; i < 8; i++)
            {
                double eeg_scale = (double)(4.5 / float ((pow (2, 23) - 1)) /
                    gain_tracker.get_gain_for_channel (i + 8) * 1000000.);
                package[i + 9] = eeg_scale * cast_24bit_to_int32 (b + 1 + 3 * i);
            }
            package[21] = (double)b[25];
            package[22] = (double)b[26];
            package[23] = (double)b[27];
            package[24] = (double)b[28];
            package[25] = (double)b[29];
            package[26] = (double)b[30];
        }
        else
        {
            for (int i = 0; i < 8; i++)
            {
                double eeg_scale = (double)(4.5 / float ((pow (2, 23) - 1)) /
                    gain_tracker.get_gain_for_channel (i) * 1000000.);
                package[i + 1] = eeg_scale * cast_24bit_to_int32 (b + 1 + 3 * i);
            }
            package[21] += (double)b[25];
            package[22] += (double)b[26];
            package[23] += (double)b[27];
            package[24] += (double)b[28];
            package[25] += (double)b[29];
            package[26] += (double)b[30];
            package[21] /= 2.0;
            package[22] /= 2.0;
            package[23] /= 2.0;
            package[24] /= 2.0;
            package[25] /= 2.0;
            package[26] /= 2.0;
            package[20] = (double)b[31];
        }

        if (b[31] == END_BYTE_STANDARD)
        {
            int32_t accel_temp[3] = {0};
            accel_temp[0] = cast_16bit_to_int32 (b + 25);
            accel_temp[1] = cast_16bit_to_int32 (b + 27);
            accel_temp[2] = cast_16bit_to_int32 (b + 29);

            if (accel_temp[0] != 0)
            {
                if (accel_count == 0)
                {
                    accel[0] = accel_scale * accel_temp[0];
                    accel[1] = accel_scale * accel_temp[1];
                    accel[2] = accel_scale * accel_temp[2];
                }
                else
                {
                    accel[0] += accel_scale * accel_temp[0];
                    accel[1] += accel_scale * accel_temp[1];
                    accel[2] += accel_scale * accel_temp[2];
                }
                accel_count++;
            }
            package[17] = (accel_count > 0) ? (accel[0] / accel_count) : accel[0];
            package[18] = (accel_count > 0) ? (accel[1] / accel_count) : accel[1];
            package[19] = (accel_count > 0) ? (accel[2] / accel_count) : accel[2];
            if (bank != 0)
            {
                package[20] = (double)b[31];
            }
        }

        if (b[31] == END_BYTE_ANALOG)
        {
            analog[0] += cast_16bit_to_int32 (b + 25);
            analog[1] += cast_16bit_to_int32 (b + 27);
            analog[2] += cast_16bit_to_int32 (b + 29);
            analog_count++;
            package[27] = (analog_count > 0) ? (analog[0] / (double)analog_count) : 0.0;
            package[28] = (analog_count > 0) ? (analog[1] / (double)analog_count) : 0.0;
            package[29] = (analog_count > 0) ? (analog[2] / (double)analog_count) : 0.0;
            if (bank != 0)
            {
                package[20] = (double)b[31];
            }
        }

        sequence_count++;
        if (sequence_count == NUM_DAISY_PACKETS)
        {
            // Keep GUI PacketLossTrackerCytonSerialDaisy (even 0,2,4,...,254):
            // same-id pairs 0,0,1,1 -> package_num 0,2,4; sequential 0,1,2,3 -> 0,2,4.
            if (raw_ids[0] == raw_ids[1])
            {
                package[pkg_ch] = (double)((raw_ids[0] * 2) & 0xFF);
            }
            else
            {
                package[pkg_ch] = (double)raw_ids[0];
            }
            package[ts_ch] = get_timestamp ();
            push_package (package);
            sequence_count = 0;
        }
    }
    delete[] package;
}
