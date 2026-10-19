package brainflow;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;

public class ExpandableEEG32WifiTest {
    
    @Test
    public void testBoardId() {
        // 验证板子ID是否正确
        assertEquals(56, BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD.get_code());
        assertEquals("EXPANDABLE_EEG_32_WIFI_BOARD", 
                    BoardIds.string_from_code(56));
    }
    
    @Test
    public void testBoardInitialization() throws BrainFlowError, IOException, ReflectiveOperationException {
        try {
            // 创建板子配置
            BrainFlowInputParams params = new BrainFlowInputParams();
            params.ip_address = "192.168.4.1";  // 默认IP地址
            params.ip_port = 8080;              // 默认端口
            
            // 创建板子控制器
            BoardShim boardShim = new BoardShim(
                BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD.get_code(), 
                params);
            
            // 准备会话
            boardShim.prepare_session();
            
            // 验证板子配置
            assertNotNull(boardShim);
            assertEquals(36, BoardShim.get_num_rows(BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD.get_code()));  // 使用静态方法获取通道数
            
            // 清理
            boardShim.release_session();
            
        } catch (BrainFlowError e) {
            fail("Board initialization failed: " + e.getMessage());
        }
    }
} 