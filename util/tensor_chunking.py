import torch.tensor
from util.utils import Utils
from modules.size_two_dimensional import SizeTwoDimensional


# This class takes care of chunking a four-dimensional image tensor with dimensions
# 1: batch_size, 2: channels, 3: height, 4: width
# into block tensors  with size 1: channels, 2: block_height, 3: block_width
# these blocks ar concatenated along the batch_size dimension, to facilitate
# parallellization of computations that are run on the blocks. Finally, the class
# contains a method "dechunk_block_tensor_concatenated_along_batch_dimension"
# that restores the original 2-dimensional block configuration. This method requires
# the block dimension to remain the same, but allows the number of channels to change.
# This is to facilitate the typical use case, where an input tensor is chunked into
# blocks, features are computed for each of these blocks with an increased number of feature
# channels in the output, and finally the output blocks are rearranged to be in the original
# input configuration.
class TensorChunking:

    def __init__(self, original_size: SizeTwoDimensional,
                 block_size: SizeTwoDimensional):
        self.original_size = original_size
        self.block_size = block_size
        TensorChunking.check_block_size_fits_into_original_size(block_size, original_size)
        self.blocks_per_row = int(original_size.width / block_size.width)
        self.blocks_per_column = int(original_size.height / block_size.height)
        self.number_of_feature_blocks_per_example = self.blocks_per_column * self.blocks_per_row
        return

    @staticmethod
    def create_tensor_chunking(original_size: SizeTwoDimensional,
                               block_size: SizeTwoDimensional):
        return TensorChunking(original_size, block_size)

    @staticmethod
    def create_indices_list(number_of_examples: int, number_of_feature_blocks_per_example: int):
        result = []
        for i in range(0, number_of_examples):
            for j in range(0, number_of_feature_blocks_per_example):
                index = i + number_of_examples * j
                result.append(index)
        return result

    @staticmethod
    def create_torch_indices_selection_tensor(number_of_examples: int, number_of_feature_blocks_per_example: int):
        indices = TensorChunking.create_indices_list(number_of_examples, number_of_feature_blocks_per_example)
        result = torch.LongTensor(indices)
        return result


    # Chunks a four-dimensional tensor into blocks.
    # The fist dimension is the batch dimension, the second dimension the input channels,
    # the third and forth dimension are the height and width respectively, along which
    # the chunking will be done. The result is returned as a list
    @staticmethod
    def chunk_tensor_into_blocks_return_as_list(
            tensor: torch.tensor, block_size: SizeTwoDimensional):
        result = list([])
        tensor_split_on_height = torch.split(tensor, block_size.height, 2)
        for row_block in tensor_split_on_height:
            blocks = torch.split(row_block, block_size.width, 3)
            result.extend(blocks)
        return result


    # Chunks a four-dimensional tensor into blocks.
    # The fist dimension is the batch dimension, the second dimension the input channels,
    # the third and forth dimension are the height and width respectively, along which
    # the chunking will be done. The result is formed by concatenating the blocks along
    # the firs (batch) dimension
    def chunk_tensor_into_blocks_concatenate_along_batch_dimension(self,
            tensor: torch.tensor):
        result = torch.zeros(0, tensor.size(1), self.block_size.height,
                             self.block_size.width)
        if Utils.use_cuda():
            # https://discuss.pytorch.org/t/which-device-is-model-tensor-stored-on/4908/7
            device = tensor.get_device()
            result = result.to(device)

        tensor_split_on_height = torch.split(tensor, self.block_size.height, 2)
        for row_block in tensor_split_on_height:
            blocks = torch.split(row_block, self.block_size.width, 3)
            list_for_cat = list([])
            list_for_cat.append(result)
            list_for_cat.extend(blocks)
            result = torch.cat(list_for_cat, 0)
            # print("result.size(): " + str(result.size()))
        return result

    @staticmethod
    def check_block_size_fits_into_original_size(block_size: SizeTwoDimensional,
            original_size: SizeTwoDimensional):
        # Check that things fit
        if (original_size.width % block_size.width) != 0:
            raise RuntimeError("Error: the original size is not a multiple of the"
                               "block size in the width dimension")

        if (original_size.height % block_size.height) != 0:
            raise RuntimeError("Error: the original size is not a multiple of the"
                               "block size in the height dimension")

    # Start from block_index 0
    def height_span(self, block_index):
        row_index = int(block_index / self.blocks_per_row)
        span_begin = row_index * self.block_size.height
        span_end = span_begin + self.block_size.height
        return span_begin, span_end

        # Start from block_index 0

    def width_span(self, block_index):
        column_index = int(block_index % self.blocks_per_row)
        span_begin = column_index * self.block_size.width
        span_end = span_begin + self.block_size.width
        return span_begin, span_end

    # Reconstructs a tensor block row from a 5 dimensional tensor whose first dimension
    # goes over the blocks int he original tensor, and whose other four dimensions go over
    # the batch dimensions, channel dimension and height and width dimensions of these blocks
    def reconstruct_tensor_bloc_row(self, tensor_grouped_by_block, row_index):
        first_block_index = row_index * self.blocks_per_row
        # The result is initialized by the first (left-most) block of the row
        result = tensor_grouped_by_block[first_block_index, :, :, :, :]

        for block_index in range(first_block_index + 1, first_block_index + self.blocks_per_row):
            # The result is gradually formed by concatenating more blocks on the right if the
            # current block, in the width dimension
            result = torch.cat((result, tensor_grouped_by_block[block_index, :, :, :, :]), 3)
        return result


    # This function performs the inverse of
    # "chunk_tensor_into_blocks_concatenate_along_batch_dimension" : it takes
    # a tensor that is chunked into blocks, with the blocks stored along the
    # first (batch) dimensions. It then reconstructs the original tensor from these blocks.
    # The reconstruction is done using the "torch.cat" method, which preserves gradient
    # information. Simply pasting over tensor slices in a newly created zeros tensor
    # leads to a faulty implementation, as this does not preserve gradient information.
    def dechunk_block_tensor_concatenated_along_batch_dimension(self, tensor: torch.tensor):
        number_of_examples = int(tensor.size(0) / self.number_of_feature_blocks_per_example)

        # print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - tensor.grad_fn "
        #      + str(tensor.grad_fn))

        # print("tensor.size(): " + str(tensor.size()))
        channels = tensor.size(1)

        tensor_grouped_by_block = tensor.view(self.number_of_feature_blocks_per_example,
                                              number_of_examples, channels,
                                              self.block_size.height, self.block_size.width)

        tensor_block_row = self.reconstruct_tensor_bloc_row(tensor_grouped_by_block, 0)
        result = tensor_block_row

        for row_index in range(1, self.blocks_per_column):
            tensor_block_row = self.reconstruct_tensor_bloc_row(tensor_grouped_by_block, row_index)
            result = torch.cat((result, tensor_block_row), 2)

        # print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - result.grad_fn "
        #      + str(result.grad_fn))

        return result

    # This is the old implementation that turns out to break the gradient
    def dechunk_block_tensor_concatenated_along_batch_dimension_breaks_gradient(self, tensor: torch.tensor):
        number_of_examples = int(tensor.size(0) / self.number_of_feature_blocks_per_example)

        print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - tensor.grad_fn "
              + str(tensor.grad_fn))

        # print("tensor.size(): " + str(tensor.size()))
        channels = tensor.size(1)

        tensor_grouped_by_block = tensor.view(self.number_of_feature_blocks_per_example,
                                              number_of_examples, channels,
                                              self.block_size.height, self.block_size.width)

        result = torch.zeros(number_of_examples, channels, self.original_size.height,
                             self.original_size.width)

        # print("tensor.nelement(): " + str(tensor.nelement()))
        # print("resuls.nelement(): " + str(result.nelement()))
        if Utils.use_cuda():
            # https://discuss.pytorch.org/t/which-device-is-model-tensor-stored-on/4908/7
            device = tensor.get_device()
            result = result.to(device)

        # print("tensor_grouped_by_block.size(): " + str(tensor_grouped_by_block.size()))
        for block_index in range(0, tensor_grouped_by_block.size(0)):
            # print("i: " + str(block_index))

            height_span_begin, height_span_end = self.height_span(block_index)
            width_span_begin, width_span_end = self.width_span(block_index)
            # print("height_span: " + str(height_span_begin) + ":"  + str(height_span_end))
            # print("width_span: " + str(width_span_begin) + ":" + str(width_span_end))

            # print("tensor_grouped_by_block[block_index, :, :, :]:" + str(
            #    tensor_grouped_by_block[block_index, :, :, :]))

            # Fixme: possibly copying like this destroys the gradient, as the grad_fn function of result
            # shows" result.grad_fn <CopySlices object at 0x7f211cbfa208>
            # instead of something like "<TanhBackward object" , "<CatBackward object"...
            # Probably "cat" should be used to reconstruct the original configuration
            # row by row. This was used previously also in the "extract_unskewed_activations"
            # function
            result[:, :, height_span_begin:height_span_end,
            width_span_begin:width_span_end] = \
                tensor_grouped_by_block[block_index, :, :, :]

        print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - result.grad_fn "
              + str(result.grad_fn))

        return result


def test_tensor_block_chunking_followed_by_dechunking_reconstructs_original():
    tensor = torch.Tensor([range(1, 97)]).view(2, 2, 4, 6)

    if Utils.use_cuda():
        tensor = tensor.cuda()

    print(tensor)
    print("tensor[0, 0, :, :]: " + str(tensor[0, 0, :, :]))
    # chunking = chunk_tensor_into_blocks_return_as_list(
    #     tensor, SizeTwoDimensional.create_size_two_dimensional(2, 2))
    # print("chunking: " + str(chunking))
    # for item in chunking:
    #     print("item.size(): " + str(item.size()))
    original_size = SizeTwoDimensional.create_size_two_dimensional(4, 6)
    block_size = SizeTwoDimensional.create_size_two_dimensional(2, 2)
    tensor_chunking = TensorChunking.create_tensor_chunking(original_size, block_size)
    chunking = tensor_chunking.chunk_tensor_into_blocks_concatenate_along_batch_dimension(tensor)
    print("chunking: " + str(chunking))
    print("chunking.size(): " + str(chunking.size()))
    dechunked_tensor = tensor_chunking.dechunk_block_tensor_concatenated_along_batch_dimension(chunking)

    print("dechunked_tensor: " + str(dechunked_tensor))

    # https://stackoverflow.com/questions/32996281/how-to-check-if-two-torch-tensors-or-matrices-are-equal
    # https://discuss.pytorch.org/t/tensor-math-logical-operations-any-and-all-functions/6624
    tensors_are_equal =  torch.eq(tensor, dechunked_tensor).all()
    print("tensors_are_equal: " + str(tensors_are_equal))
    if not tensors_are_equal:
        raise RuntimeError("Error: original tensor " + str(tensor) +
                           " and dechunked tensor " + str(dechunked_tensor) +
                           " are not equal")
    else:
        print("Success: original tensor and dechunked(chunked(tensor)) are equal")


def main():
    test_tensor_block_chunking_followed_by_dechunking_reconstructs_original()


if __name__ == "__main__":
    main()