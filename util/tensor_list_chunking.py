import torch.tensor
from util.utils import Utils
from modules.size_two_dimensional import SizeTwoDimensional
from util.tensor_chunking import TensorChunking

# This class takes care of chunking a list of four-dimensional image tensors with
# list elements of the dimensions
# 1: channels, 2: height, 3: width
# into block tensors  with size 1: channels, 2: block_height, 3: block_width
# these blocks are concatenated along the batch_size dimension, to facilitate
# parallellization of computations that are run on the blocks. Finally, the class
# contains a method "dechunk_block_tensor_concatenated_along_batch_dimension"
# that restores the original list, 2-dimensional block configuration. This method requires
# the block dimension to remain the same, but allows the number of channels to change.
# This is to facilitate the typical use case, where an input tensor is chunked into
# blocks, features are computed for each of these blocks with an increased number of feature
# channels in the output, and finally the output blocks are rearranged to be in the original
# input configuration.
# This class is similar to TensorChunking, but the functionality is changed
# to the scenario where there is a list of 3d tensors of different sizes
# to be chunked into one tensor of blocks and then reconstructed to the original
# size, rather than a 4-dimensional tensor with the first dimension the batch
# dimension.


class TensorListChunking:

    def __init__(self, original_sizes: SizeTwoDimensional,
                 block_size: SizeTwoDimensional):
        self.original_sizes = original_sizes
        self.block_size = block_size
        TensorListChunking.check_block_size_fits_into_original_sizes(block_size, original_sizes)
        return

    @staticmethod
    def create_tensor_list_chunking(tensor_list: list,
                               block_size: SizeTwoDimensional):
        return TensorListChunking(TensorListChunking.get_original_sizes_from_tensor_list(tensor_list), block_size)

    @staticmethod
    def get_original_sizes_from_tensor_list(tensor_list: list):
        result = list([])
        for x in tensor_list:
            original_size = SizeTwoDimensional.create_size_two_dimensional(x.size(1), x.size(2))
            result.append(original_size)
        return result


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

    def chunk_tensor_list_into_blocks_concatenate_along_batch_dimension_cat_once(self,
                                                                                 tensor_list: list):

        # New implementation: collect everything and call torch.cat only once
        list_for_cat = list([])

        for tensor in tensor_list:
            # A dimension 0 must be added with unsqueeze,
            # for concatenation along the batch dimension later on
            tensor = tensor.unsqueeze(0)
            tensor_split_on_height = torch.split(tensor, self.block_size.height, 2)

            for row_block in tensor_split_on_height:
                blocks = torch.split(row_block, self.block_size.width, 3)
                # print("blocks: " + str(blocks))
                list_for_cat.extend(blocks)
        result = torch.cat(list_for_cat, 0)
        # print("chunk_tensor_into_blocks_concatenate_along_batch_dimension - result.size(): " + str(result.size()))

        return result

    # Chunks a list of three-dimensional tensors into blocks.
    # The first element dimension is the input channels,
    # the second and third dimension are the height and width respectively, along which
    # the chunking will be done. The result is formed by concatenating the blocks along
    # a new batch dimension
    def chunk_tensor_list_into_blocks_concatenate_along_batch_dimension(self,
            tensor: torch.tensor):
        return self.chunk_tensor_list_into_blocks_concatenate_along_batch_dimension_cat_once(tensor)

        # No-cat implementation: slower on loss.backward
        # return self.chunk_tensor_into_blocks_concatenate_along_batch_dimension_no_cat(tensor)

    @staticmethod
    def check_block_size_fits_into_original_sizes(block_size: SizeTwoDimensional,
                                                  original_sizes: list):
        for original_size in original_sizes:
            TensorChunking.check_block_size_fits_into_original_size(block_size, original_size)

    # Reconstruct the tensor block row, using a combination of torch.split, squeeze and torch.cat operations
    # which for some reason yields better loss.backward performance than the original
    # implementation using torch.cat with a for loop and slicing
    @staticmethod
    def reconstruct_tensor_block_row_split_squeeze_cat(tensor_grouped_by_block, row_index, blocks_per_row):
        first_block_index = row_index * blocks_per_row

        row_slice = tensor_grouped_by_block[first_block_index:first_block_index+blocks_per_row, :, :, :]
        tensors_split = torch.split(row_slice, 1, 0)
        # print("tensors_split[0].size(): " + str(tensors_split[0].size()))
        # Splitting still retains the extra first dimension, which must be removed then
        # for all list elements using squeeze
        tensors_split_squeezed = list([])
        for element in tensors_split:
            tensors_split_squeezed.append(element.squeeze(0))
        # In "one go" with a combination of split, squeeze and cat
        return torch.cat(tensors_split_squeezed, 2)

    # Reconstructs a tensor block row from a 4 dimensional tensor whose first dimension
    # goes over the blocks int the original tensor, and whose other three dimensions go over
    # the channel dimension and height and width dimensions of these blocks
    @staticmethod
    def reconstruct_tensor_block_row(tensor_grouped_by_block, row_index, blocks_per_row):
        # return self.reconstruct_tensor_block_row_original(tensor_grouped_by_block, row_index)
        # This implementation somehow yields much faster loss.backward performance than the original
        return TensorListChunking.reconstruct_tensor_block_row_split_squeeze_cat(tensor_grouped_by_block, row_index,
                                                                   blocks_per_row)

    def get_number_of_blocks_for_example(self, example_index):
        original_size = self.original_sizes[example_index]
        blocks_per_row = int(original_size.width / self.block_size.width)
        blocks_per_column = int(original_size.height / self.block_size.height)
        number_of_feature_blocks_example = blocks_per_column * blocks_per_row
        return blocks_per_column, blocks_per_row, number_of_feature_blocks_example


    # This function performs the inverse of
    # "chunk_tensor_into_blocks_concatenate_along_batch_dimension" : it takes
    # a tensor that is chunked into blocks, with the blocks stored along the
    # first (batch) dimensions. It then reconstructs the original tensor from these blocks.
    # The reconstruction is done using the "torch.cat" method, which preserves gradient
    # information. Simply pasting over tensor slices in a newly created zeros tensor
    # leads to a faulty implementation, as this does not preserve gradient information.
    def dechunk_block_tensor_concatenated_along_batch_dimension_changed_block_size(self, tensor: torch.tensor,
                                                                                   block_size: SizeTwoDimensional):
        number_of_examples = len(self.original_sizes)

        # print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - tensor.grad_fn "
        #      + str(tensor.grad_fn))

        # print("tensor.size(): " + str(tensor.size()))
        channels = tensor.size(1)

        result = list([])

        blocks_start_index = 0
        for example_index in range(0, number_of_examples):
            blocks_per_column, blocks_per_row, blocks_for_example = self.get_number_of_blocks_for_example(example_index)
            blocks_end_index = blocks_start_index + blocks_for_example
            example_sub_tensor = tensor[blocks_start_index:blocks_end_index]
            # print("example_sub_tensor: " + str(example_sub_tensor))

            tensor_grouped_by_block = example_sub_tensor.view(blocks_for_example, channels,
                                                              block_size.height, block_size.width)
            # print("tensor_grouped_by_block: " + str(tensor_grouped_by_block))

            tensor_block_row = TensorListChunking.reconstruct_tensor_block_row(tensor_grouped_by_block, 0, blocks_per_row)
            reconstructed_example_tensor = tensor_block_row

            for row_index in range(1, blocks_per_column):
                tensor_block_row = TensorListChunking.reconstruct_tensor_block_row(tensor_grouped_by_block, row_index, blocks_per_row)
                reconstructed_example_tensor = torch.cat((reconstructed_example_tensor, tensor_block_row), 1)

            result.append(reconstructed_example_tensor)

            # print(">>> dechunk_block_tensor_concatenated_along_batch_dimension: - result.grad_fn "
            #      + str(result.grad_fn))

            blocks_start_index += blocks_for_example

        return result

    def dechunk_block_tensor_concatenated_along_batch_dimension(self, tensor: torch.tensor):
        return self.dechunk_block_tensor_concatenated_along_batch_dimension_changed_block_size(tensor, self.block_size)


def test_tensor_list_block_chunking_followed_by_dechunking_reconstructs_original():
    tensor_one = torch.Tensor([range(1, 49)]).view(2, 4, 6)
    tensor_two = torch.Tensor([range(1, 17)]).view(2, 2, 4)

    if Utils.use_cuda():
        tensor_one = tensor_one.cuda()
        tensor_two = tensor_two.cuda()

    print(tensor_one)
    print("tensor_one[0,  :, :]: " + str(tensor_one[0, :, :]))
    print("tensor_two[0,  :, :]: " + str(tensor_two[0, :, :]))

    block_size = SizeTwoDimensional.create_size_two_dimensional(2, 2)
    tensor_list = list([tensor_one, tensor_two])
    tensor_chunking = TensorListChunking.create_tensor_list_chunking(tensor_list, block_size)
    chunking = tensor_chunking.chunk_tensor_list_into_blocks_concatenate_along_batch_dimension(tensor_list)
    print("chunking: " + str(chunking))
    print("chunking.size(): " + str(chunking.size()))
    dechunked_tensor_list = tensor_chunking.dechunk_block_tensor_concatenated_along_batch_dimension_changed_block_size(chunking)

    print("dechunked_tensor_list: " + str(dechunked_tensor_list))

    # https://stackoverflow.com/questions/32996281/how-to-check-if-two-torch-tensors-or-matrices-are-equal
    # https://discuss.pytorch.org/t/tensor-math-logical-operations-any-and-all-functions/6624
    for tensor_original, tensor_reconstructed in zip(tensor_list, dechunked_tensor_list):
        tensors_are_equal =  torch.eq(tensor_original, tensor_reconstructed).all()
        print("tensors_are_equal: " + str(tensors_are_equal))
        if not tensors_are_equal:
            raise RuntimeError("Error: original tensor " + str(tensor_original) +
                               " and dechunked tensor " + str(tensor_reconstructed) +
                               " are not equal")
        else:
            print("Success: original tensor and dechunked(chunked(tensor)) are equal")


def main():
    test_tensor_list_block_chunking_followed_by_dechunking_reconstructs_original()


if __name__ == "__main__":
    main()